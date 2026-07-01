from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import config_path, load_config, resolve_path
from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.common.utils import stable_id


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def load_project_config(path: str | Path = "configs/knowledge_sources_config.yaml") -> dict[str, Any]:
    return load_config(path)


def load_relative_yaml(config: dict[str, Any], path: str | Path) -> dict[str, Any]:
    return read_yaml(resolve_path(path, Path(config["_project_root"])))


def source_path(config: dict[str, Any], key: str, default: str) -> Path:
    return config_path(config, key, default)


def make_id(prefix: str, *parts: Any) -> str:
    return stable_id(prefix, *parts)
