from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_csv, write_csv, write_json
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, HypothesisStatus


def dump_hypothesis(hypothesis: HypothesisRecord) -> dict[str, Any]:
    return hypothesis.model_dump(mode="json")


def save_hypothesis_outputs(hypotheses: list[HypothesisRecord], top_k: list[HypothesisRecord], config: dict[str, Any]) -> dict[str, str]:
    root = Path(config["_project_root"])
    outputs = config.get("outputs", {})
    pool_path = resolve_path(outputs["hypothesis_pool"], root)
    registry_path = resolve_path(outputs["hypothesis_registry"], root)
    top_path = resolve_path(outputs["top_k_hypotheses"], root)
    write_json(pool_path, [dump_hypothesis(item) for item in hypotheses])
    rows = []
    for item in hypotheses:
        rows.append(
            {
                "hypothesis_id": item.hypothesis_id,
                "title": item.title,
                "mechanism": item.mechanism,
                "status": item.status.value if hasattr(item.status, "value") else item.status,
                "evidence_level": item.evidence_level.value if hasattr(item.evidence_level, "value") else item.evidence_level,
                "pre_analysis_score": item.pre_analysis_score,
                "parent_id": item.parent_id or "",
                "used_data_features": ";".join(item.used_data_features),
            }
        )
    write_csv(registry_path, rows)
    write_json(top_path, [dump_hypothesis(item) for item in top_k])
    return {
        "hypothesis_pool": str(pool_path),
        "hypothesis_registry": str(registry_path),
        "top_k_hypotheses": str(top_path),
    }


def update_registry_status(registry_path: str | Path, hypothesis_id: str, status: HypothesisStatus | str) -> None:
    path = Path(registry_path)
    rows = read_csv(path) if path.exists() else []
    value = status.value if hasattr(status, "value") else str(status)
    for row in rows:
        if row.get("hypothesis_id") == hypothesis_id:
            row["status"] = value
    write_csv(path, rows)
