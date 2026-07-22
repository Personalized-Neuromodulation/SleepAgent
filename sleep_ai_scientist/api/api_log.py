from __future__ import annotations

import json
from pathlib import Path

from sleep_ai_scientist.common.io import ensure_parent
from sleep_ai_scientist.schemas.api import APICallLog


def append_api_logs(path: str | Path, logs: list[APICallLog]) -> None:
    target = Path(path)
    ensure_parent(target)
    with target.open("a", encoding="utf-8") as f:
        for log in logs:
            f.write(json.dumps(log.model_dump(mode="json"), ensure_ascii=False) + "\n")
