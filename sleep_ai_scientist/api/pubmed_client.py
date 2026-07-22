from __future__ import annotations

import os
from typing import Any

from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.normalizer import make_api_record
from sleep_ai_scientist.schemas.api import APISearchResult


class PubMedClient:
    provider = "pubmed"

    def __init__(self, base_client: BaseAPIClient, provider_config: dict[str, Any]):
        self.base = base_client
        self.config = provider_config

    def search(self, query: str, max_results: int = 20) -> APISearchResult:
        warnings = []
        email = os.getenv(self.config.get("email_env", "NCBI_EMAIL"), "")
        tool = os.getenv(self.config.get("tool_env", "NCBI_TOOL"), "SleepAgent")
        api_key = os.getenv(self.config.get("api_key_env", "NCBI_API_KEY"), "")
        if not email:
            warnings.append("NCBI email missing")
        params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": max_results, "tool": tool, "email": email}
        if api_key:
            params["api_key"] = api_key
        search_payload = self.base.get("esearch.fcgi", params=params, query=query)
        ids = search_payload.get("esearchresult", {}).get("idlist", []) if search_payload else []
        if not ids:
            return APISearchResult(provider=self.provider, query=query, count=0, records=[], warnings=warnings)
        summary_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json", "tool": tool, "email": email}
        if api_key:
            summary_params["api_key"] = api_key
        payload = self.base.get("esummary.fcgi", params=summary_params, query=query)
        result = payload.get("result", {}) if payload else {}
        records = []
        for pmid in result.get("uids", ids):
            item = result.get(str(pmid), {})
            article_ids = item.get("articleids", [])
            doi = next((x.get("value") for x in article_ids if x.get("idtype") == "doi"), None)
            pmcid = next((x.get("value") for x in article_ids if x.get("idtype") == "pmc"), None)
            year = None
            if str(item.get("pubdate", ""))[:4].isdigit():
                year = int(str(item.get("pubdate"))[:4])
            records.append(make_api_record(self.provider, str(pmid), item.get("title", ""), abstract=item.get("abstract"), year=year, doi=doi, pmid=str(pmid), pmcid=pmcid, url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", source="api:pubmed", journal=item.get("fulljournalname"), authors=[a.get("name") for a in item.get("authors", []) if a.get("name")], keywords=[], citation_count=None, is_open_access=None, raw=item))
        return APISearchResult(provider=self.provider, query=query, count=len(records), records=records, warnings=warnings)
