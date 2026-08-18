# -*- coding: utf-8 -*-
import logging
import os
import time
from datetime import date, datetime

import requests

from parser.text_cleanup import clean_metadata_text


logger = logging.getLogger(__name__)


class MetadataDiscoveryService:
    CROSSREF_API = "https://api.crossref.org/works"
    EUROPE_PMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    OPENALEX_API = "https://api.openalex.org/works"
    SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(
        self,
        sources=None,
        rows=50,
        max_pages_per_keyword=2,
        timeout=15,
        min_interval=0.5,
        mailto=None,
        openalex_api_key=None,
        semantic_scholar_api_key=None,
        journal_name=None,
        session=None,
    ):
        self.sources = [str(source).strip().lower() for source in (sources or []) if str(source).strip()]
        self.rows = max(1, min(100, int(rows or 50)))
        self.max_pages_per_keyword = max(1, int(max_pages_per_keyword or 1))
        self.timeout = max(1, int(timeout or 15))
        self.min_interval = max(0.0, float(min_interval or 0))
        self.mailto = (mailto or os.getenv("CROSSREF_MAILTO") or os.getenv("EUROPE_PMC_EMAIL") or "").strip()
        self.openalex_api_key = (openalex_api_key or os.getenv("OPENALEX_API_KEY") or "").strip()
        self.semantic_scholar_api_key = (
            semantic_scholar_api_key
            or os.getenv("S2_API_KEY")
            or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
            or ""
        ).strip()
        self.journal_name = clean_metadata_text(journal_name or "")
        self.session = session or requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "crawler2025-metadata-discovery/1.0",
        })
        self._last_request_time = 0.0

    def discover(self, keywords, start_date, end_date):
        rows = []
        seen = set()
        for keyword in [str(value).strip() for value in (keywords or []) if str(value).strip()]:
            for source in self.sources:
                for article in self._discover_source(source, keyword, start_date, end_date):
                    key = (str(article.get("doi") or "").lower(), str(article.get("title") or "").lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    article["matched_keyword"] = keyword
                    article["metadata_sources"] = article.get("source", source)
                    rows.append(article)
        return rows

    def _discover_source(self, source, keyword, start_date, end_date):
        fetcher = {
            "crossref": self._fetch_crossref,
            "europe_pmc": self._fetch_europe_pmc,
            "openalex": self._fetch_openalex,
            "semantic_scholar": self._fetch_semantic_scholar,
        }.get(source)
        if not fetcher:
            logger.warning("Unknown metadata discovery source skipped: %s", source)
            return []
        try:
            return fetcher(keyword, start_date, end_date)
        except Exception as exc:
            logger.warning("Metadata discovery %s failed keyword=%s: %s", source, keyword, exc)
            return []

    def _fetch_crossref(self, keyword, start_date, end_date):
        rows = []
        cursor = "*"
        for _ in range(self.max_pages_per_keyword):
            params = {
                "query": keyword,
                "filter": ",".join([
                    "from-pub-date:%s" % self._date_text(start_date),
                    "until-pub-date:%s" % self._date_text(end_date),
                    "type:journal-article",
                ]),
                "rows": self.rows,
                "cursor": cursor,
                "sort": "published",
                "order": "desc",
            }
            if self.journal_name:
                params["query.container-title"] = self.journal_name
            if self.mailto:
                params["mailto"] = self.mailto
            message = self._get_json(self.CROSSREF_API, params=params).get("message") or {}
            items = message.get("items") or []
            rows.extend(self._map_crossref(item) for item in items)
            cursor = message.get("next-cursor") or ""
            if not items or not cursor or len(items) < self.rows:
                break
        return [row for row in rows if row.get("title")]

    def _fetch_europe_pmc(self, keyword, start_date, end_date):
        rows = []
        for page in range(1, self.max_pages_per_keyword + 1):
            params = {
                "query": '%s AND FIRST_PDATE:[%s TO %s]' % (
                    self._source_query(keyword, source="europe_pmc"),
                    self._date_text(start_date),
                    self._date_text(end_date),
                ),
                "format": "json",
                "resultType": "core",
                "pageSize": self.rows,
                "page": page,
            }
            if self.mailto:
                params["email"] = self.mailto
            results = (((self._get_json(self.EUROPE_PMC_API, params=params).get("resultList") or {}).get("result")) or [])
            rows.extend(self._map_europe_pmc(item) for item in results)
            if len(results) < self.rows:
                break
        return [row for row in rows if row.get("title")]

    def _fetch_openalex(self, keyword, start_date, end_date):
        rows = []
        for page in range(1, self.max_pages_per_keyword + 1):
            params = {
                "search": self._source_query(keyword, source="openalex"),
                "filter": ",".join([
                    "from_publication_date:%s" % self._date_text(start_date),
                    "to_publication_date:%s" % self._date_text(end_date),
                    "type:article",
                ]),
                "per-page": self.rows,
                "page": page,
            }
            if self.mailto:
                params["mailto"] = self.mailto
            if self.openalex_api_key:
                params["api_key"] = self.openalex_api_key
            results = self._get_json(self.OPENALEX_API, params=params).get("results") or []
            rows.extend(self._map_openalex(item) for item in results)
            if len(results) < self.rows:
                break
        return [row for row in rows if row.get("title")]

    def _fetch_semantic_scholar(self, keyword, start_date, end_date):
        rows = []
        start_year = self._year(start_date)
        end_year = self._year(end_date)
        headers = {}
        if self.semantic_scholar_api_key:
            headers["x-api-key"] = self.semantic_scholar_api_key
        for page in range(self.max_pages_per_keyword):
            params = {
                "query": self._source_query(keyword, source="semantic_scholar"),
                "fields": "title,abstract,year,authors,externalIds,url,venue,publicationDate",
                "limit": self.rows,
                "offset": page * self.rows,
                "year": "%s-%s" % (start_year, end_year),
            }
            payload = self._get_json(self.SEMANTIC_SCHOLAR_API, params=params, headers=headers)
            items = payload.get("data") or []
            rows.extend(self._map_semantic_scholar(item) for item in items)
            if len(items) < self.rows:
                break
        return [row for row in rows if row.get("title")]

    def _get_json(self, url, params=None, headers=None):
        self._throttle()
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _throttle(self):
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _map_crossref(self, item):
        doi = str(item.get("DOI") or "").strip()
        title = self._first(item.get("title"))
        journal = self._first(item.get("container-title"))
        return {
            "title": clean_metadata_text(title),
            "abstract": clean_metadata_text(item.get("abstract") or ""),
            "date": self._crossref_date(item),
            "doi": doi,
            "url": "https://doi.org/%s" % doi if doi else str(item.get("URL") or ""),
            "authors": self._crossref_authors(item),
            "journal": journal,
            "article_type": item.get("subtype") or item.get("type") or "",
            "source": "crossref",
        }

    def _map_europe_pmc(self, item):
        doi = str(item.get("doi") or "").strip()
        return {
            "title": clean_metadata_text(item.get("title") or ""),
            "abstract": clean_metadata_text(item.get("abstractText") or ""),
            "date": item.get("firstPublicationDate") or item.get("pubYear") or "",
            "doi": doi,
            "url": self._europe_pmc_url(item, doi),
            "authors": item.get("authorString") or "",
            "journal": item.get("journalTitle") or "",
            "article_type": item.get("pubType") or "",
            "source": "europe_pmc",
        }

    def _map_openalex(self, item):
        doi = str(item.get("doi") or "").strip()
        doi = doi[len("https://doi.org/"):] if doi.lower().startswith("https://doi.org/") else doi
        return {
            "title": clean_metadata_text(item.get("title") or ""),
            "abstract": clean_metadata_text(self._openalex_abstract(item.get("abstract_inverted_index"))),
            "date": item.get("publication_date") or "",
            "doi": doi,
            "url": "https://doi.org/%s" % doi if doi else str(item.get("id") or ""),
            "authors": "; ".join(
                ((authorship.get("author") or {}).get("display_name") or "")
                for authorship in item.get("authorships") or []
                if ((authorship.get("author") or {}).get("display_name") or "")
            ),
            "journal": ((item.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
            "article_type": item.get("type") or "",
            "source": "openalex",
        }

    def _map_semantic_scholar(self, item):
        external_ids = item.get("externalIds") or {}
        doi = str(external_ids.get("DOI") or "").strip()
        return {
            "title": clean_metadata_text(item.get("title") or ""),
            "abstract": clean_metadata_text(item.get("abstract") or ""),
            "date": item.get("publicationDate") or item.get("year") or "",
            "doi": doi,
            "url": item.get("url") or ("https://doi.org/%s" % doi if doi else ""),
            "authors": "; ".join(author.get("name") or "" for author in item.get("authors") or [] if author.get("name")),
            "journal": item.get("venue") or "",
            "article_type": "",
            "source": "semantic_scholar",
        }

    def _crossref_date(self, item):
        for key in ("published-print", "published-online", "published", "issued"):
            parts = (item.get(key) or {}).get("date-parts") or []
            if not parts or not parts[0]:
                continue
            values = list(parts[0]) + [1, 1]
            return "%04d-%02d-%02d" % (int(values[0]), int(values[1]), int(values[2]))
        return ""

    def _crossref_authors(self, item):
        authors = []
        for author in item.get("author") or []:
            name = " ".join(part for part in (author.get("given"), author.get("family")) if part)
            if name:
                authors.append(name)
        return "; ".join(authors)

    def _openalex_abstract(self, inverted_index):
        if not isinstance(inverted_index, dict):
            return ""
        words = []
        for word, positions in inverted_index.items():
            for position in positions or []:
                words.append((int(position), word))
        return " ".join(word for _, word in sorted(words))

    def _europe_pmc_url(self, item, doi):
        urls = item.get("fullTextUrlList", {})
        if isinstance(urls, dict):
            values = urls.get("fullTextUrl") or []
            if values and isinstance(values[0], dict):
                return values[0].get("url") or ""
        return "https://doi.org/%s" % doi if doi else ""

    def _first(self, value):
        if isinstance(value, list):
            return str(value[0] or "") if value else ""
        return str(value or "")

    def _source_query(self, keyword, source):
        keyword = str(keyword or "").strip()
        if not self.journal_name:
            return keyword
        if source == "europe_pmc":
            return '%s AND JOURNAL:"%s"' % (keyword, self.journal_name)
        return '%s "%s"' % (keyword, self.journal_name)

    def _date_text(self, value):
        if isinstance(value, datetime):
            value = value.date()
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def _year(self, value):
        if isinstance(value, (date, datetime)):
            return value.year
        text = str(value or "")
        return int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else datetime.now().year
