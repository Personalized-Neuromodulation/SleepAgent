from __future__ import annotations

from typing import Any

from sleep_ai_scientist.memory.scientific_memory import append_event


def record_hypothesis_event(event_type: str, hypothesis_id: str, payload: dict[str, Any] | None = None) -> str:
    data = {"hypothesis_id": hypothesis_id}
    if payload:
        data.update(payload)
    return append_event(f"hypothesis.{event_type}", data)
