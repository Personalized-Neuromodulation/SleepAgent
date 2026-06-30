from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_csv


def cfg_path(config: dict[str, Any], section: str, key: str) -> Path:
    return resolve_path(config.get(section, {}).get(key, ""))


def input_path(config: dict[str, Any], key: str) -> Path:
    return cfg_path(config, "inputs", key)


def output_path(config: dict[str, Any], key: str) -> Path:
    return cfg_path(config, "outputs", key)


def subject_column(rows: list[dict[str, str]], config: dict[str, Any]) -> str:
    if not rows:
        return config.get("subject_id", {}).get("column", "subject_id")
    candidates = [config.get("subject_id", {}).get("column", "subject_id"), *config.get("subject_id", {}).get("aliases", [])]
    columns = set(rows[0])
    for candidate in candidates:
        if candidate in columns:
            return candidate
    raise ValueError(f"No subject id column found. Candidates={candidates}")


def normalize_subject_rows(rows: list[dict[str, str]], config: dict[str, Any]) -> list[dict[str, str]]:
    column = subject_column(rows, config)
    normalized = []
    for row in rows:
        item = dict(row)
        item["subject_id"] = str(row.get(column, "")).strip()
        normalized.append(item)
    return [row for row in normalized if row.get("subject_id")]


def read_input_rows(config: dict[str, Any], key: str) -> list[dict[str, str]]:
    path = input_path(config, key)
    return normalize_subject_rows(read_csv(path), config) if path.exists() else []


def is_missing(value: Any) -> bool:
    return str(value).strip() in {"", "NA", "N/A", "nan", "None", "null"}


def infer_dtype(values: list[str]) -> str:
    observed = [value for value in values if not is_missing(value)]
    if not observed:
        return "unknown"
    try:
        for value in observed:
            float(value)
        return "numeric"
    except ValueError:
        return "categorical"
