from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import config_path
from sleep_ai_scientist.common.io import write_json


def build_corpus_manifest(
    config: dict[str, Any],
    corpus_version: str,
    api_summary: dict[str, Any],
    notes: str = "Phase 1 Grounding Corpus v1",
) -> dict[str, Any]:
    api_cfg = config.get("api", {})
    providers = [
        provider
        for provider, provider_cfg in api_cfg.get("providers", {}).items()
        if provider_cfg.get("enabled", False)
    ]
    query_set = config.get("query_set", {})
    return {
        "corpus_version": corpus_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "query_set_version": query_set.get("version", ""),
        "api_enabled": bool(api_cfg.get("enabled", False)),
        "providers": providers,
        "seed_literature_file": str(config_path(config, "seed_papers")),
        "api_literature_csv": str(config_path(config, "api_literature_csv", api_cfg.get("output", {}).get("api_literature_csv", "data/literature/api_retrieved_papers.csv"))),
        "final_literature_registry": str(config_path(config, "literature_registry_csv", "data/literature/literature_registry.csv")),
        "evidence_table": str(config_path(config, "output_grounding_dir") / "evidence_table.csv"),
        "mechanism_graph": str(config_path(config, "output_grounding_dir") / "mechanism_graph.json"),
        "evidence_to_variable_map": str(config_path(config, "output_grounding_dir") / "evidence_to_variable_map.yaml"),
        "analysis_ready_profile": str(config_path(config, "output_profiles_dir") / "analysis_ready_profile.yaml"),
        "grounding_qc_report": str(config_path(config, "output_grounding_dir") / "grounding_qc_report.json"),
        "api_search_log": str(config_path(config, "api_search_log", api_cfg.get("output", {}).get("api_search_log", "outputs/grounding/api_search_log.jsonl"))),
        "query_results": api_summary.get("query_results", []),
        "notes": notes,
    }


def write_corpus_manifest(path: Path, manifest: dict[str, Any]) -> None:
    write_json(path, manifest)
