from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.api.api_log import append_api_logs
from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.cache import APICache
from sleep_ai_scientist.api.europe_pmc_client import EuropePMCClient
from sleep_ai_scientist.api.normalizer import api_to_literature_record, deduplicate_api_records
from sleep_ai_scientist.api.openalex_client import OpenAlexClient
from sleep_ai_scientist.api.pubmed_client import PubMedClient
from sleep_ai_scientist.api.rate_limiter import RateLimiter
from sleep_ai_scientist.api.semantic_scholar_client import SemanticScholarClient
from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import ensure_parent, write_csv
from sleep_ai_scientist.schemas.api import APILiteratureRecord, APISearchResult
from sleep_ai_scientist.schemas.literature import LiteratureRecord

CLIENTS = {
    "pubmed": PubMedClient,
    "europe_pmc": EuropePMCClient,
    "openalex": OpenAlexClient,
    "semantic_scholar": SemanticScholarClient,
}


def _rps(provider: str, provider_cfg: dict[str, Any]) -> float:
    if provider == "pubmed":
        import os

        key = os.getenv(provider_cfg.get("api_key_env", "NCBI_API_KEY"), "")
        return float(provider_cfg.get("requests_per_second_with_key" if key else "requests_per_second_without_key", 3))
    return float(provider_cfg.get("requests_per_second", 1))


def build_client(provider: str, config: dict[str, Any], session: Any | None = None, rate_limit_enabled: bool = True):
    api_cfg = config.get("api", {})
    provider_cfg = api_cfg.get("providers", {}).get(provider, {})
    cache = APICache(resolve_path(api_cfg.get("cache_dir", ".cache/sleepagent_api"), Path(config["_project_root"])), bool(api_cfg.get("cache_enabled", True)))
    base = BaseAPIClient(
        provider=provider,
        base_url=provider_cfg.get("base_url", ""),
        timeout_seconds=float(api_cfg.get("timeout_seconds", 20)),
        max_retries=int(api_cfg.get("max_retries", 3)),
        backoff_seconds=float(api_cfg.get("backoff_seconds", 1.5)),
        cache=cache,
        rate_limiter=RateLimiter(_rps(provider, provider_cfg), enabled=rate_limit_enabled),
        session=session,
        fail_open=bool(api_cfg.get("fail_open", True)),
    )
    return CLIENTS[provider](base, provider_cfg)


def search_literature_apis(config: dict[str, Any], session: Any | None = None, rate_limit_enabled: bool = True) -> tuple[list[LiteratureRecord], dict[str, Any]]:
    api_cfg = config.get("api", {})
    if not api_cfg.get("enabled", False):
        return [], {"enabled": False, "results": [], "deduplicated_count": 0, "warnings": []}
    max_results = int(api_cfg.get("max_results_per_query", 20))
    queries = api_cfg.get("search_queries", [])
    all_records: list[APILiteratureRecord] = []
    results: list[APISearchResult] = []
    logs = []
    warnings = []
    for provider, provider_cfg in api_cfg.get("providers", {}).items():
        if not provider_cfg.get("enabled", False) or provider not in CLIENTS:
            continue
        client = build_client(provider, config, session=session, rate_limit_enabled=rate_limit_enabled)
        for query in queries:
            try:
                result = client.search(query, max_results=max_results)
                results.append(result)
                all_records.extend(result.records)
                warnings.extend(result.warnings)
            except Exception as exc:
                warnings.append(f"{provider}:{query}:{exc}")
                if not api_cfg.get("fail_open", True):
                    raise
        logs.extend(client.base.logs)
    deduped = deduplicate_api_records(all_records)
    root = Path(config["_project_root"])
    output_cfg = api_cfg.get("output", {})
    csv_path = resolve_path(output_cfg.get("api_literature_csv", "data/literature/api_retrieved_papers.csv"), root)
    jsonl_path = resolve_path(output_cfg.get("api_literature_jsonl", "data/literature/api_retrieved_papers.jsonl"), root)
    log_path = resolve_path(output_cfg.get("api_search_log", "outputs/grounding/api_search_log.jsonl"), root)
    write_csv(csv_path, [_csv_row(item) for item in deduped])
    ensure_parent(jsonl_path)
    with jsonl_path.open("w", encoding="utf-8") as f:
        for item in deduped:
            f.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n")
    append_api_logs(log_path, logs)
    literature = [api_to_literature_record(item) for item in deduped]
    summary = {
        "enabled": True,
        "provider_counts": _provider_counts(results),
        "query_count": len(queries),
        "raw_count": len(all_records),
        "deduplicated_count": len(deduped),
        "warnings": warnings,
        "cache_enabled": bool(api_cfg.get("cache_enabled", True)),
        "cache_dir": api_cfg.get("cache_dir"),
        "csv_path": str(csv_path),
        "jsonl_path": str(jsonl_path),
        "log_path": str(log_path),
    }
    return literature, summary


def _provider_counts(results: list[APISearchResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.provider] = counts.get(result.provider, 0) + result.count
    return counts


def _csv_row(item: APILiteratureRecord) -> dict[str, Any]:
    payload = item.model_dump(mode="json")
    payload["authors"] = ";".join(payload.get("authors") or [])
    payload["keywords"] = ";".join(payload.get("keywords") or [])
    payload.pop("raw", None)
    return payload
