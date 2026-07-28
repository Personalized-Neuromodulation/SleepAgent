from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import load_config


def load_literature_db_config(path: str | Path) -> dict[str, Any]:
    return load_config(path)


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}
