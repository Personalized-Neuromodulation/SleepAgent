from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_yaml


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_path(value: str | Path, base_dir: Path | None = None) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir or project_root()) / path


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = resolve_path(config_path)
    config = read_yaml(path)
    config["_config_path"] = str(path)
    config["_project_root"] = str(project_root())
    return config


def config_path(config: dict[str, Any], key: str, default: str | None = None) -> Path:
    paths = config.get("paths", {})
    value = paths.get(key, default)
    if value is None:
        raise KeyError(f"Missing config path: {key}")
    return resolve_path(value)


def existing_or_fixture(config: dict[str, Any], primary_key: str, fixture_key: str) -> Path:
    primary = config_path(config, primary_key)
    if primary.exists() and primary.stat().st_size > 0:
        return primary
    return config_path(config, fixture_key)
