from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_csv, read_json, read_yaml


def input_path(config: dict[str, Any], key: str) -> Path:
    return resolve_path(config.get("inputs", {})[key], Path(config["_project_root"]))


def output_path(config: dict[str, Any], key: str) -> Path:
    return resolve_path(config.get("outputs", {})[key], Path(config["_project_root"]))


def load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = read_json(path)
    return payload if isinstance(payload, list) else []


def load_hypotheses(config: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for key in ("hypothesis_pool", "top_k_hypotheses", "co_scientist_top_k"):
        path = input_path(config, key)
        for item in load_json_list(path):
            hid = item.get("hypothesis_id")
            if hid and hid not in seen:
                seen.add(hid)
                rows.append(item)
    return rows


def analysis_ready_variables(config: dict[str, Any]) -> set[str]:
    path = input_path(config, "analysis_ready_profile")
    profile = read_yaml(path) if path.exists() else {"features": []}
    return {item.get("feature_name") for item in profile.get("features", []) if item.get("feature_name")} | {"group"}


def evidence_ids(config: dict[str, Any]) -> set[str]:
    path = input_path(config, "evidence_table")
    return {row.get("evidence_id") for row in read_csv(path)} if path.exists() else set()


def model_dump_rows(items: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        rows.append({key: ";".join(value) if isinstance(value, list) else value for key, value in payload.items()})
    return rows


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default
