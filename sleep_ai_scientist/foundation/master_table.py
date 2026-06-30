from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_csv, write_csv
from sleep_ai_scientist.foundation.subject_index import FEATURE_INPUTS
from sleep_ai_scientist.foundation.utils import input_path, normalize_subject_rows


def _merge_value(target: dict[str, Any], column: str, value: Any, modality: str, duplicate_log: list[dict[str, str]]) -> None:
    if column not in target:
        target[column] = value
        return
    if target[column] == value or value in {"", None}:
        return
    prefixed = f"{modality}_{column}"
    target[prefixed] = value
    duplicate_log.append({"column": column, "renamed_to": prefixed, "modality": modality})


def build_multimodal_master_table(config: dict[str, Any], subject_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_subject = {row["subject_id"]: dict(row) for row in subject_rows}
    duplicate_log: list[dict[str, str]] = []
    coverage: dict[str, int] = {}
    input_files = 0
    for modality, key in FEATURE_INPUTS.items():
        path = input_path(config, key)
        if not path.exists():
            coverage[modality] = 0
            continue
        input_files += 1
        rows = normalize_subject_rows(read_csv(path), config)
        coverage[modality] = len({row["subject_id"] for row in rows})
        for row in rows:
            subject_id = row["subject_id"]
            target = by_subject.setdefault(subject_id, {"subject_id": subject_id})
            for column, value in row.items():
                if column == "subject_id":
                    continue
                _merge_value(target, column, value, modality, duplicate_log)
    rows = list(by_subject.values())
    columns = []
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    normalized_rows = [{column: row.get(column, "") for column in columns} for row in rows]
    log = {
        "input_file_count": input_files,
        "subject_count": len(normalized_rows),
        "modality_subject_coverage": coverage,
        "merged_column_count": len(columns),
        "duplicate_columns": duplicate_log,
    }
    return normalized_rows, log


def write_master_table(rows: list[dict[str, Any]], path: Path) -> None:
    write_csv(path, rows)
