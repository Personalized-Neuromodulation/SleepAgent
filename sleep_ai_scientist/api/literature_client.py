from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.cache import APICache
from sleep_ai_scientist.api.europe_pmc_client import EuropePMCClient
from sleep_ai_scientist.api.normalizer import api_to_literature_record, deduplicate_api_records
from sleep_ai_scientist.api.openalex_client import OpenAlexClient
from sleep_ai_scientist.api.pubmed_client import PubMedClient
from sleep_ai_scientist.api.rate_limiter import RateLimiter
from sleep_ai_scientist.api.semantic_scholar_client import SemanticScholarClient
from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import write_csv
from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.literature.query_loader import select_query_payload
from sleep_ai_scientist.schemas.api import APILiteratureRecord, APISearchResult
from sleep_ai_scientist.schemas.literature import LiteratureRecord

CLIENTS = {
    "pubmed": PubMedClient,
    "europe_pmc": EuropePMCClient,
    "openalex": OpenAlexClient,
    "semantic_scholar": SemanticScholarClient,
}


def load_env_file(path: Path, *, override: bool = False) -> list[str]:
    """Load simple KEY=VALUE pairs so CLI API builds can use a local .env."""
    if not path.exists():
        return []
    loaded = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value
            loaded.append(key)
    return loaded


def apply_query_config(config: dict[str, Any], query_config_path: str | Path | None, *, query_scope: str = "library") -> dict[str, Any]:
    """Overlay a versioned literature query set onto an API config."""
    if not query_config_path:
        return config
    root = Path(config["_project_root"])
    payload = select_query_payload(read_yaml(resolve_path(query_config_path, root)), scope=query_scope)
    query_groups = payload.get("queries", {})
    queries: list[str] = []
    for values in query_groups.values():
        for query in values or []:
            if str(query) not in queries:
                queries.append(str(query))
    settings = payload.get("settings", {})
    api_cfg = config.setdefault("api", {})
    api_cfg["search_queries"] = queries
    if "max_results_per_query" in settings:
        api_cfg["max_results_per_query"] = int(settings["max_results_per_query"])
    provider_allowlist = {str(item) for item in settings.get("providers", [])}
    if provider_allowlist:
        for provider, provider_cfg in api_cfg.get("providers", {}).items():
            provider_cfg["enabled"] = provider in provider_allowlist
    config["query_set"] = {
        "version": payload.get("query_set", {}).get("version", ""),
        "description": payload.get("query_set", {}).get("description", ""),
        "scope": payload.get("scope", query_scope),
        "query_config_path": str(resolve_path(query_config_path, root)),
        "query_groups": {key: list(value or []) for key, value in query_groups.items()},
        "settings": settings,
    }
    return config


def _rps(provider: str, provider_cfg: dict[str, Any]) -> float:
    if provider_cfg.get("min_interval_seconds") is not None:
        interval = max(float(provider_cfg["min_interval_seconds"]), 0.001)
        return 1.0 / interval
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
    load_env_file(Path(config["_project_root"]) / ".env")
    max_results = int(api_cfg.get("max_results_per_query", 20))
    queries = api_cfg.get("search_queries", [])
    verbose = bool(api_cfg.get("verbose", False) or os.getenv("SLEEPAGENT_API_VERBOSE", "").lower() in {"1", "true", "yes"})
    verbose_detail = bool(api_cfg.get("verbose_detail", False) or os.getenv("SLEEPAGENT_API_VERBOSE_DETAIL", "").lower() in {"1", "true", "yes"})
    compact_progress = bool(api_cfg.get("progress", True)) and verbose and not verbose_detail
    progress_every = max(1, int(api_cfg.get("progress_update_every", max(1, len(queries) // 10 or 1))))
    all_records: list[APILiteratureRecord] = []
    results: list[APISearchResult] = []
    logs = []
    warnings = []
    if verbose:
        enabled = [name for name, cfg in api_cfg.get("providers", {}).items() if cfg.get("enabled", False) and name in CLIENTS]
        print(f"[api] enabled providers: {', '.join(enabled) or 'none'}", flush=True)
        print(f"[api] query count: {len(queries)}; max_results_per_query: {max_results}", flush=True)
    for provider, provider_cfg in api_cfg.get("providers", {}).items():
        if not provider_cfg.get("enabled", False) or provider not in CLIENTS:
            continue
        progress = _APIProgress(provider, len(queries), progress_every=progress_every) if compact_progress else None
        if verbose and not compact_progress:
            print(f"[api:{provider}] start", flush=True)
        client = build_client(provider, config, session=session, rate_limit_enabled=rate_limit_enabled)
        provider_records = 0
        provider_warnings = 0
        if progress:
            progress.update(0, records=provider_records, warnings=provider_warnings)
        for index, query in enumerate(queries, start=1):
            if verbose_detail:
                print(f"[api:{provider}] query {index}/{len(queries)}: {query}", flush=True)
            try:
                result = client.search(query, max_results=max_results)
                for record in result.records:
                    record.query = query
                results.append(result)
                all_records.extend(result.records)
                warnings.extend(result.warnings)
                provider_records += result.count
                provider_warnings += len(result.warnings)
                if verbose_detail:
                    print(f"[api:{provider}] -> {result.count} records", flush=True)
            except Exception as exc:
                warnings.append(f"{provider}:{query}:{exc}")
                provider_warnings += 1
                if verbose_detail:
                    print(f"[api:{provider}] warning: {exc}", flush=True)
                if not api_cfg.get("fail_open", True):
                    raise
            if progress:
                progress.update(index, records=provider_records, warnings=provider_warnings)
        logs.extend(client.base.logs)
        if progress:
            progress.done(records=provider_records, warnings=provider_warnings, accumulated=len(all_records))
        elif verbose:
            print(f"[api:{provider}] done; accumulated raw records: {len(all_records)}", flush=True)
    deduped = deduplicate_api_records(all_records)
    if verbose:
        print(f"[api] deduplicated records: {len(deduped)}", flush=True)
    root = Path(config["_project_root"])
    output_cfg = api_cfg.get("output", {})
    csv_path = resolve_path(output_cfg.get("api_literature_csv", "outputs/grounding/api_retrieved_papers.csv"), root)
    write_csv(csv_path, [_csv_row(item) for item in deduped])
    literature = [api_to_literature_record(item) for item in deduped]
    errors = [f"{log.provider}:{log.query}:{log.error}" for log in logs if not log.success and log.error]
    cache_hit_count = sum(1 for log in logs if log.cached)
    summary = {
        "enabled": True,
        "provider_counts": _provider_counts(results),
        "query_results": [
            {
                "provider": result.provider,
                "query": result.query,
                "retrieved_at": max((record.retrieved_at for record in result.records), default=""),
                "result_count": result.count,
            }
            for result in results
        ],
        "query_count": len(queries),
        "raw_count": len(all_records),
        "deduplicated_count": len(deduped),
        "errors": errors,
        "warnings": warnings + errors,
        "cache_enabled": bool(api_cfg.get("cache_enabled", True)),
        "cache_hit_count": cache_hit_count,
        "cache_dir": api_cfg.get("cache_dir"),
        "csv_path": str(csv_path),
    }
    return literature, summary


class _APIProgress:
    def __init__(self, provider: str, total: int, *, progress_every: int = 1, width: int = 24) -> None:
        self.provider = provider
        self.total = max(0, total)
        self.progress_every = max(1, progress_every)
        self.width = max(10, width)
        self._last_step = -1
        self._interactive = sys.stdout.isatty()

    def update(self, current: int, *, records: int, warnings: int) -> None:
        if not self._interactive:
            return
        current = min(max(0, current), self.total)
        if current not in {0, self.total} and current - self._last_step < self.progress_every:
            return
        self._last_step = current
        sys.stdout.write("\r\033[K" + self._line(current, records=records, warnings=warnings))
        sys.stdout.flush()

    def done(self, *, records: int, warnings: int, accumulated: int) -> None:
        prefix = "\r\033[K" if self._interactive else ""
        sys.stdout.write(prefix + f"{self._line(self.total, records=records, warnings=warnings)} done accumulated_raw={accumulated}" + "\n")
        sys.stdout.flush()

    def _line(self, current: int, *, records: int, warnings: int) -> str:
        if self.total:
            filled = int(round((current / self.total) * self.width))
        else:
            filled = self.width
        bar = "#" * filled + "-" * (self.width - filled)
        return f"[api:{self.provider}] [{bar}] {current}/{self.total} records={records} warnings={warnings}"


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
