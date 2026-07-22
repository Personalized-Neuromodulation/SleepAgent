from __future__ import annotations

import os
from typing import Any

from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.normalizer import make_api_record
from sleep_ai_scientist.schemas.api import APISearchResult


class SemanticScholarClient:
    provider = "semantic_scholar"

    def __init__(self, base_client: BaseAPIClient, provider_config: dict[str, Any]):
        self.base = base_client
        self.config = provider_config

    def search(self, query: str, max_results: int = 20) -> APISearchResult:
        api_key = os.getenv(self.config.get("api_key_env", "SEMANTIC_SCHOLAR_API_KEY"), "")
        headers = {"x-api-key": api_key} if api_key else {}
        params = {"query": query, "limit": max_results, "fields": "paperId,title,abstract,year,authors,venue,externalIds,citationCount,url,isOpenAccess"}
        payload = self.base.get("paper/search", params=params, headers=headers, query=query)
        records = []
        for item in payload.get("data", []) if payload else []:
            external = item.get("externalIds") or {}
            records.append(make_api_record(self.provider, item.get("paperId"), item.get("title", ""), abstract=item.get("abstract"), year=item.get("year"), doi=external.get("DOI"), pmid=external.get("PubMed"), pmcid=external.get("PubMedCentral"), url=item.get("url"), source="api:semantic_scholar", journal=item.get("venue"), authors=[a.get("name") for a in item.get("authors", []) if a.get("name")], keywords=[], citation_count=item.get("citationCount"), citation_source="semantic_scholar", is_open_access=item.get("isOpenAccess"), raw=item))
        return APISearchResult(provider=self.provider, query=query, count=len(records), records=records, warnings=[])
