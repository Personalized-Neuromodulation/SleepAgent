from __future__ import annotations

import os
from typing import Any

from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.normalizer import make_api_record, openalex_abstract
from sleep_ai_scientist.schemas.api import APISearchResult


class OpenAlexClient:
    provider = "openalex"

    def __init__(self, base_client: BaseAPIClient, provider_config: dict[str, Any]):
        self.base = base_client
        self.config = provider_config

    def search(self, query: str, max_results: int = 20) -> APISearchResult:
        params = {"search": query, "per_page": max_results, "select": "id,doi,title,display_name,publication_year,cited_by_count,abstract_inverted_index,authorships,primary_location,open_access"}
        api_key = os.getenv(self.config.get("api_key_env", "OPENALEX_API_KEY"), "")
        if api_key:
            params["api_key"] = api_key
        payload = self.base.get("works", params=params, query=query)
        records = []
        for item in payload.get("results", []) if payload else []:
            location = item.get("primary_location") or {}
            source = location.get("source") or {}
            records.append(make_api_record(self.provider, item.get("id"), item.get("display_name") or item.get("title") or "", abstract=openalex_abstract(item.get("abstract_inverted_index")), year=item.get("publication_year"), doi=item.get("doi"), pmid=None, pmcid=None, url=item.get("id"), source="api:openalex", journal=source.get("display_name") if isinstance(source, dict) else None, authors=[a.get("author", {}).get("display_name") for a in item.get("authorships", []) if a.get("author", {}).get("display_name")], keywords=[], citation_count=item.get("cited_by_count"), is_open_access=(item.get("open_access") or {}).get("is_oa"), raw=item))
        return APISearchResult(provider=self.provider, query=query, count=len(records), records=records, warnings=[])
