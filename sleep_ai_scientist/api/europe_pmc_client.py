from __future__ import annotations

from typing import Any

from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.normalizer import make_api_record
from sleep_ai_scientist.schemas.api import APISearchResult


class EuropePMCClient:
    provider = "europe_pmc"

    def __init__(self, base_client: BaseAPIClient, provider_config: dict[str, Any]):
        self.base = base_client
        self.config = provider_config

    def search(self, query: str, max_results: int = 20) -> APISearchResult:
        payload = self.base.get("search", params={"query": query, "format": "json", "pageSize": max_results, "resultType": "core"}, query=query)
        rows = payload.get("resultList", {}).get("result", []) if payload else []
        records = []
        for item in rows:
            year = int(item["pubYear"]) if str(item.get("pubYear", "")).isdigit() else None
            records.append(make_api_record(self.provider, item.get("id"), item.get("title", ""), abstract=item.get("abstractText"), year=year, doi=item.get("doi"), pmid=item.get("pmid"), pmcid=item.get("pmcid"), url=item.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url") if isinstance(item.get("fullTextUrlList"), dict) else None, source="api:europe_pmc", journal=item.get("journalTitle"), authors=[x.strip() for x in str(item.get("authorString", "")).split(",") if x.strip()], keywords=[], citation_count=int(item["citedByCount"]) if str(item.get("citedByCount", "")).isdigit() else None, is_open_access=str(item.get("isOpenAccess", "")).lower() == "y", raw=item))
        return APISearchResult(provider=self.provider, query=query, count=len(records), records=records, warnings=[])
