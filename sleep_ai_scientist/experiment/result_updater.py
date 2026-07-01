from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_csv, read_json, write_csv, write_json
from sleep_ai_scientist.memory.null_registry import append_null_finding
from sleep_ai_scientist.memory.result_memory import record_result_summary


STATUS_BY_DECISION = {
    "accepted": "accepted",
    "revised": "revised",
    "rejected": "rejected",
    "hold": "hold",
    "exploratory_only": "revised",
}


def update_results_into_registry(config: dict[str, Any], reviews: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    root = Path(config["_project_root"])
    inputs = config.get("inputs", {})
    registry_path = resolve_path(inputs.get("hypothesis_registry", "outputs/hypotheses/hypothesis_registry.csv"), root)
    lineage_path = resolve_path(inputs.get("hypothesis_lineage", "outputs/hypotheses/hypothesis_lineage.json"), root)
    rows = read_csv(registry_path) if registry_path.exists() else []
    by_result = {item["experiment_id"]: item for item in results}
    changed = 0
    null_count = 0
    for review in reviews:
        status = STATUS_BY_DECISION.get(review.get("decision"), "hold")
        for row in rows:
            if row.get("hypothesis_id") == review.get("hypothesis_id"):
                row["status"] = status
                changed += 1
        result = by_result.get(review["experiment_id"], {})
        record_result_summary(result, review)
        if review.get("decision") in {"rejected", "hold", "exploratory_only"}:
            append_null_finding(review, result)
            null_count += 1
    write_csv(registry_path, rows)
    if lineage_path.exists():
        lineage = read_json(lineage_path)
        for node in lineage.get("nodes", []):
            for review in reviews:
                if node.get("hypothesis_id") == review.get("hypothesis_id"):
                    node["status"] = STATUS_BY_DECISION.get(review.get("decision"), "hold")
        write_json(lineage_path, lineage)
    return {"registry_updates": changed, "null_registry_updates": null_count}
