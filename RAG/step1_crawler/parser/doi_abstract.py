# -*- coding: utf-8 -*-
import logging
import os
import re
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

from parser.text_cleanup import clean_metadata_text


logger = logging.getLogger(__name__)


class DoiAbstractFetcher:
    """Fetch abstracts by DOI from metadata APIs, without visiting publisher pages."""

    DEFAULT_EMAIL = "m1993615519@163.com"
    DEFAULT_OPENALEX_API_KEY = "RbfrULWTgikcvf6HTt8K2P"
    DEFAULT_S2_API_KEY = "s2k-UBcTYeR1Wu6oLdOPEooueysXchKs0pu26A1Zv2vd"

    CROSSREF_API = "https://api.crossref.org/works"
    EUROPE_PMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    OPENALEX_API = "https://api.openalex.org/works"
    SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper"

    def __init__(self, session=None, timeout=12, mailto=None, openalex_api_key=None, semantic_scholar_api_key=None):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.mailto = (
            mailto
            or os.getenv("CROSSREF_MAILTO")
            or os.getenv("EUROPE_PMC_EMAIL")
            or self.DEFAULT_EMAIL
        ).strip()
        self.openalex_api_key = (
            openalex_api_key
            or os.getenv("OPENALEX_API_KEY", self.DEFAULT_OPENALEX_API_KEY)
        ).strip()
        self.s2_api_key = (
            semantic_scholar_api_key
            or os.getenv("S2_API_KEY")
            or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
            or self.DEFAULT_S2_API_KEY
        ).strip()
        self.semantic_scholar_api_key = self.s2_api_key
        self.cache = {}
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "crawler2025-doi-abstract/1.0 (mailto:%s)" % (self.mailto or "unknown@example.com"),
        })
        # Each repair worker owns its own DoiAbstractFetcher/Session.
        # Keep HTTP retries disabled here so 4 worker threads do not multiply
        # one 429/timeout into a retry storm.
        adapter = HTTPAdapter(
            max_retries=0,
            pool_connections=4,
            pool_maxsize=4,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch_by_doi(self, doi):
        normalized = self.normalize_doi(doi)
        if not normalized:
            return {}
        key = normalized.lower()
        if key in self.cache:
            return dict(self.cache[key])

        for source, fetcher in (
            ("crossref", self._fetch_crossref),
            ("europe_pmc", self._fetch_europe_pmc),
            ("openalex", self._fetch_openalex),
            ("semantic_scholar", self._fetch_semantic_scholar),
        ):
            try:
                result = fetcher(normalized)
            except Exception as exc:
                logger.debug("DOI abstract fetch %s failed doi=%s: %s", source, normalized, exc)
                continue
            abstract = self.clean_text((result or {}).get("abstract") or "")
            if abstract:
                result = dict(result or {})
                result["doi"] = normalized
                result["abstract"] = abstract
                result["source"] = source
                self.cache[key] = result
                return dict(result)

        self.cache[key] = {}
        return {}

    def _fetch_crossref(self, doi):
        response = self.session.get(
            "%s/%s" % (self.CROSSREF_API, quote(doi, safe="")),
            timeout=self.timeout,
        )
        if response.status_code != 200:
            return {}
        item = (response.json().get("message") or {})
        return {
            "title": self._first(item.get("title")),
            "abstract": item.get("abstract") or "",
            "date": self._date_from_crossref(item),
            "journal": self._first(item.get("container-title")),
            "authors": self._authors_from_crossref(item),
            "url": "https://doi.org/%s" % doi,
        }

    def _fetch_europe_pmc(self, doi):
        params = {
            "query": 'DOI:"%s"' % doi,
            "format": "json",
            "resultType": "core",
            "pageSize": 5,
        }
        if self.mailto:
            params["email"] = self.mailto
        response = self.session.get(self.EUROPE_PMC_API, params=params, timeout=self.timeout)
        if response.status_code != 200:
            return {}
        results = (((response.json().get("resultList") or {}).get("result")) or [])
        target = doi.lower()
        for item in results:
            if self.normalize_doi(item.get("doi")) == target:
                return {
                    "title": item.get("title") or "",
                    "abstract": item.get("abstractText") or "",
                    "date": item.get("firstPublicationDate") or item.get("pubYear") or "",
                    "journal": item.get("journalTitle") or "",
                    "authors": item.get("authorString") or "",
                    "url": item.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url", "") if isinstance(item.get("fullTextUrlList"), dict) else "",
                }
        return {}

    def _fetch_openalex(self, doi):
        params = {}
        if self.openalex_api_key:
            params["api_key"] = self.openalex_api_key
        response = self.session.get(
            "%s/%s" % (self.OPENALEX_API, quote("doi:%s" % doi, safe=":")),
            params=params,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            return {}
        item = response.json()
        return {
            "title": item.get("title") or "",
            "abstract": self._openalex_abstract(item.get("abstract_inverted_index")),
            "date": item.get("publication_date") or "",
            "journal": ((item.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
            "authors": "; ".join(
                ((a.get("author") or {}).get("display_name") or "")
                for a in item.get("authorships") or []
                if ((a.get("author") or {}).get("display_name") or "")
            ),
            "url": "https://doi.org/%s" % doi,
        }

    def _fetch_semantic_scholar(self, doi):
        headers = {}
        if self.semantic_scholar_api_key:
            headers["x-api-key"] = self.semantic_scholar_api_key
        response = self.session.get(
            "%s/%s" % (self.SEMANTIC_SCHOLAR_API, quote("DOI:%s" % doi, safe=":")),
            params={"fields": "title,abstract,year,authors,externalIds,url"},
            headers=headers,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            return {}
        item = response.json()
        return {
            "title": item.get("title") or "",
            "abstract": item.get("abstract") or "",
            "date": item.get("year") or "",
            "authors": "; ".join(a.get("name") or "" for a in item.get("authors") or [] if a.get("name")),
            "url": item.get("url") or "",
        }

    def _openalex_abstract(self, inverted_index):
        if not isinstance(inverted_index, dict) or not inverted_index:
            return ""
        positioned = []
        for word, positions in inverted_index.items():
            for pos in positions or []:
                positioned.append((int(pos), word))
        return " ".join(word for _, word in sorted(positioned))

    def _date_from_crossref(self, item):
        for key in ("published-print", "published-online", "published", "issued"):
            parts = (item.get(key) or {}).get("date-parts") or []
            if parts and parts[0]:
                values = list(parts[0]) + [1, 1]
                return "%04d-%02d-%02d" % (int(values[0]), int(values[1]), int(values[2]))
        return ""

    def _authors_from_crossref(self, item):
        authors = []
        for author in item.get("author") or []:
            name = " ".join(part for part in [author.get("given"), author.get("family")] if part)
            if name:
                authors.append(name)
        return "; ".join(authors)

    def _first(self, values):
        if isinstance(values, list) and values:
            return str(values[0] or "")
        return str(values or "")

    @classmethod
    def normalize_doi(cls, value):
        text = str(value or "").strip()
        text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text, flags=re.I)
        text = re.sub(r"^doi:\s*", "", text, flags=re.I)
        text = text.strip().rstrip('.,;)"\'')
        return text.lower()

    @classmethod
    def clean_text(cls, value):
        text = clean_metadata_text(value)
        text = re.sub(r"^(abstract|summary)\b\s*[:：.-]\s*", "", text, flags=re.I)
        text = re.sub(r"^(abstract|summary)\b\s+", "", text, flags=re.I)
        return text.strip(" :：-")
