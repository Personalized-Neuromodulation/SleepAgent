from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from .models import CrawledPaperMetadata


def is_sciencedirect_journal(url: str | None) -> bool:
    return bool(url and "sciencedirect.com/journal/" in url.casefold())


def fetch_sciencedirect_search(http, journal, query: str, api_key: str, count: int = 20):
    """Search ScienceDirect through Elsevier's documented, authenticated API."""

    if not api_key:
        return [], {
            "code": "ELSEVIER_API_KEY_MISSING",
            "message": "Set ELSEVIER_API_KEY to use the official ScienceDirect Search API",
            "retryable": False,
        }
    identifier = journal.issn or journal.eissn
    scope = f"ISSN({identifier.replace('-', '')})" if identifier else f"pub-name({journal.title})"
    api_query = f"{scope} AND ({query})"
    url = "https://api.elsevier.com/content/search/sciencedirect?" + urlencode(
        {"query": api_query, "count": min(max(int(count), 1), 100), "httpAccept": "application/json"}
    )
    status, body, final, _ = http.get(
        url,
        use_cache=False,
        headers={"X-ELS-APIKey": api_key, "Accept": "application/json"},
    )
    if status != 200:
        message = f"Elsevier ScienceDirect Search API returned HTTP {status}"
        try:
            payload = json.loads(body)
            message = (
                payload.get("service-error", {}).get("status", {}).get("statusText")
                or payload.get("error-response", {}).get("error-message")
                or message
            )
        except Exception:
            pass
        return [], {
            "code": "ELSEVIER_API_ERROR",
            "message": message,
            "http_status": status,
            "retryable": status in {429, 500, 502, 503, 504},
        }
    payload = json.loads(body)
    entries = payload.get("search-results", {}).get("entry", []) or []
    return [sciencedirect_entry_to_metadata(entry, final, query) for entry in entries], None


def sciencedirect_entry_to_metadata(entry: dict, api_url: str, query: str) -> CrawledPaperMetadata:
    links = entry.get("link") or []
    if isinstance(links, dict):
        links = [links]
    source_url = next(
        (link.get("@href") for link in links if link.get("@ref") in {"scidir", "self"} and link.get("@href")),
        entry.get("prism:url") or entry.get("dc:identifier") or api_url,
    )
    raw_doi = entry.get("prism:doi") or entry.get("dc:identifier") or ""
    doi_match = re.search(r"10\.\d{4,9}/\S+", str(raw_doi))
    doi = doi_match.group(0).rstrip(" .") if doi_match else None
    authors = []
    raw_authors = (entry.get("authors") or {}).get("author") or []
    if isinstance(raw_authors, dict):
        raw_authors = [raw_authors]
    for author in raw_authors:
        name = author.get("$") or author.get("authname") or author.get("dc:creator") or ""
        bits = str(name).split()
        if bits:
            authors.append({"given_name": " ".join(bits[:-1]) or None, "family_name": bits[-1], "raw": author})
    return CrawledPaperMetadata(
        source_url=str(source_url),
        title=str(entry.get("dc:title") or entry.get("title") or "").strip(),
        authors=authors,
        abstract=entry.get("dc:description") or entry.get("description"),
        journal=entry.get("prism:publicationName"),
        publication_date=entry.get("prism:coverDate") or entry.get("prism:coverDisplayDate"),
        doi=doi,
        volume=entry.get("prism:volume"),
        issue=entry.get("prism:issueIdentifier"),
        pages=entry.get("prism:pageRange"),
        article_type="journal-article",
        raw_metadata={"science_direct_entry": entry, "_official_api_search": {"query": query, "api_url": api_url}},
        discovery_channel="publisher_api",
        discovery_provider="elsevier_sciencedirect",
    )
