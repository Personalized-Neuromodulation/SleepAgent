from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import project_root
from sleep_ai_scientist.common.io import read_csv, write_csv


def append_null_finding(review: dict[str, Any], result: dict[str, Any], path: str | Path = "outputs/memory/null_findings_registry.csv") -> str:
    target = project_root() / Path(path)
    rows = read_csv(target) if target.exists() else []
    key = (review.get("experiment_id"), review.get("hypothesis_id"))
    rows = [row for row in rows if (row.get("experiment_id"), row.get("hypothesis_id")) != key]
    rows.append(
        {
            "experiment_id": review.get("experiment_id"),
            "hypothesis_id": review.get("hypothesis_id"),
            "decision": review.get("decision"),
            "n_used": result.get("n_used"),
            "summary": review.get("summary"),
        }
    )
    write_csv(target, rows)
    return str(target)
