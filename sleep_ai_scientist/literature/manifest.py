from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_json


def build_library_manifest(library_version: str, query_set_version: str, paths: dict[str, str], counts: dict[str, Any], notes: str = "") -> dict[str, Any]:
    return {
        "library_version": library_version,
        "query_set_version": query_set_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "registry_csv": paths.get("registry_csv", ""),
        "registry_jsonl": paths.get("registry_jsonl", ""),
        "provider_summary": paths.get("provider_summary", ""),
        "query_summary": paths.get("query_summary", ""),
        "coverage_audit": paths.get("coverage_audit", ""),
        "anchor_papers": paths.get("anchor_papers", ""),
        "query_expansion_candidates": paths.get("query_expansion_candidates", ""),
        "counts": counts,
        "notes": notes,
    }


def write_library_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    write_json(Path(path), manifest)

