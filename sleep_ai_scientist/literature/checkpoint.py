from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_json


def checkpoint_dir(run_dir: str | Path) -> Path:
    path = Path(run_dir) / "checkpoints"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_checkpoint(run_dir: str | Path, payload: dict[str, Any], iteration: int | None = None) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"iter_{iteration:03d}" if iteration is not None else "latest"
    path = checkpoint_dir(run_dir) / f"checkpoint_{suffix}_{timestamp}.json"
    data = {"timestamp": datetime.now(timezone.utc).isoformat(), "iteration": iteration, **payload}
    write_json(path, data)
    write_json(checkpoint_dir(run_dir) / "latest_checkpoint.json", data | {"checkpoint_path": str(path)})
    return path


def load_checkpoint(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_latest_checkpoint(run_dir: str | Path) -> Path | None:
    path = checkpoint_dir(run_dir) / "latest_checkpoint.json"
    return path if path.exists() else None

