from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import load_config, resolve_path
from sleep_ai_scientist.common.io import read_yaml, write_yaml
from sleep_ai_scientist.literature.library_builder import run_literature_build
from sleep_ai_scientist.literature.query_loader import select_query_payload


def _limited_query_config(base_query_config: str | Path, output_path: str | Path, max_queries: int) -> Path:
    payload = select_query_payload(read_yaml(Path(base_query_config)), scope="library")
    remaining = max_queries
    limited: dict[str, list[str]] = {}
    for group, queries in payload.get("queries", {}).items():
        if remaining <= 0:
            limited[group] = []
            continue
        selected = list(queries or [])[:remaining]
        limited[group] = selected
        remaining -= len(selected)
    payload["queries"] = limited
    output = Path(output_path)
    write_yaml(output, payload)
    return output


def run_iteration(config: dict[str, Any], iteration: int, run_dir: str | Path, *, dry_run: bool = False, backend: str | None = "sqlite") -> dict[str, Any]:
    root = Path(config.get("_project_root", Path.cwd()))
    base_config = resolve_path(config.get("inputs", {}).get("base_config", "configs/literature_library_config.yaml"), root)
    query_config = resolve_path(config.get("inputs", {}).get("initial_query_config", "configs/literature_queries.yaml"), root)
    max_queries = int(config.get("api", {}).get("max_queries_per_iteration", 30))
    limited_query = _limited_query_config(query_config, Path(run_dir) / f"iteration_{iteration:03d}_queries.yaml", max_queries)
    if dry_run:
        return {
            "iteration": iteration,
            "dry_run": True,
            "base_config": str(base_config),
            "query_config": str(limited_query),
            "planned_max_queries": max_queries,
            "status": "planned",
        }
    base_payload = load_config(base_config)
    base_payload.setdefault("api", {})["max_results_per_query"] = int(config.get("api", {}).get("max_results_per_query", 50))
    if config.get("api", {}).get("cache_enabled") is not None:
        base_payload["api"]["cache_enabled"] = bool(config.get("api", {}).get("cache_enabled"))
    temp_base = Path(run_dir) / f"iteration_{iteration:03d}_library_config.yaml"
    write_yaml(temp_base, {k: v for k, v in base_payload.items() if not k.startswith("_")})
    return run_literature_build(temp_base, query_config_path=limited_query, library_version=config.get("project", {}).get("target_library_version"), backend=backend)
