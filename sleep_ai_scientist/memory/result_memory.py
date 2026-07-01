from __future__ import annotations

from typing import Any

from sleep_ai_scientist.memory.scientific_memory import append_event


def record_result_summary(result: dict[str, Any], review: dict[str, Any] | None = None) -> str:
    payload = {
        "experiment_id": result.get("experiment_id"),
        "hypothesis_id": result.get("hypothesis_id"),
        "n_used": result.get("n_used"),
        "status": result.get("status"),
        "decision": review.get("decision") if review else None,
    }
    return append_event("result.summary", payload)
