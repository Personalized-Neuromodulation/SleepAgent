from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.knowledge_sources.base import make_id


def build_instrument_records(config: dict[str, Any], source_path: str | Path = "configs/instruments_registry.yaml") -> list[dict[str, Any]]:
    payload = read_yaml(resolve_path(source_path, Path(config["_project_root"])))
    records = []
    for abbreviation, data in payload.get("instruments", {}).items():
        records.append(
            {
                "instrument_id": make_id("instrument", abbreviation),
                "name": data.get("name", abbreviation),
                "abbreviation": abbreviation,
                "domain": data.get("domain", ""),
                "score_range": str(data.get("score_range", "")),
                "direction": data.get("direction", ""),
                "cutoffs_json": data.get("common_cutoffs", []),
                "license_status": data.get("license_status", "check_before_use"),
                "reference": data.get("reference", ""),
                "role_json": data.get("role", []),
                "notes": data.get("notes", "Cutoffs are context-dependent and not universal truth."),
            }
        )
    return records

