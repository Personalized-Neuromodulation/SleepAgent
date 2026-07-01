from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import project_root
from sleep_ai_scientist.common.io import ensure_parent


def append_event(event_type: str, payload: dict[str, Any], path: str | Path = "outputs/memory/scientific_memory.jsonl") -> str:
    target = project_root() / Path(path)
    ensure_parent(target)
    row = {"created_at": datetime.now(timezone.utc).isoformat(), "event_type": event_type, "payload": payload}
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return str(target)
