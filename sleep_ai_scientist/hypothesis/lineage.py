from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_json, write_json
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord


def build_lineage(hypotheses: list[HypothesisRecord]) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "hypothesis_id": item.hypothesis_id,
                "parent_id": item.parent_id,
                "status": item.status.value if hasattr(item.status, "value") else item.status,
                "evidence_level": item.evidence_level.value if hasattr(item.evidence_level, "value") else item.evidence_level,
                "source": item.source,
            }
            for item in hypotheses
        ],
        "edges": [
            {"parent_id": item.parent_id, "child_id": item.hypothesis_id}
            for item in hypotheses
            if item.parent_id
        ],
    }


def save_lineage(hypotheses: list[HypothesisRecord], config: dict[str, Any]) -> str:
    root = Path(config["_project_root"])
    path = resolve_path(config.get("outputs", {})["hypothesis_lineage"], root)
    write_json(path, build_lineage(hypotheses))
    return str(path)


def next_revision_id(parent_id: str, lineage_path: str | Path) -> str:
    path = Path(lineage_path)
    existing = read_json(path).get("nodes", []) if path.exists() else []
    prefix = f"{parent_id}_v"
    versions = []
    for node in existing:
        hid = node.get("hypothesis_id", "")
        if hid.startswith(prefix):
            try:
                versions.append(int(hid.replace(prefix, "")))
            except ValueError:
                continue
    return f"{parent_id}_v{max(versions, default=1) + 1}"
