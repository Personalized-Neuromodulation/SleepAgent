from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_csv, write_csv
from sleep_ai_scientist.foundation.subject_index import FEATURE_INPUTS
from sleep_ai_scientist.foundation.utils import infer_dtype, input_path, is_missing, normalize_subject_rows
from sleep_ai_scientist.schemas.foundation import FeatureRegistryRecord, FeatureRole


COVARIATES = {"age", "sex", "education", "medication", "mean_FD", "in_scanner_sleep_time"}
SCALES = {"ISI", "PSQI", "anxiety_score", "depression_score"}


def infer_role(column: str) -> FeatureRole:
    if column == "group":
        return FeatureRole.group
    if column in COVARIATES:
        return FeatureRole.covariate
    if column in SCALES:
        return FeatureRole.scale if column not in {"ISI", "PSQI"} else FeatureRole.outcome
    if column.lower().startswith("qc"):
        return FeatureRole.qc
    return FeatureRole.feature


def _stats(rows: list[dict[str, str]], column: str) -> tuple[float, int, str]:
    values = [row.get(column, "") for row in rows]
    total = len(values) or 1
    available = sum(1 for value in values if not is_missing(value))
    return round(1 - available / total, 3), available, infer_dtype(values)


def scan_feature_tables(config: dict[str, Any]) -> list[FeatureRegistryRecord]:
    records: list[FeatureRegistryRecord] = []
    subject_column_names = {"subject_id", *config.get("subject_id", {}).get("aliases", [])}
    for modality, key in FEATURE_INPUTS.items():
        path = input_path(config, key)
        if not path.exists():
            continue
        rows = normalize_subject_rows(read_csv(path), config)
        if not rows:
            continue
        for column in rows[0]:
            if column in subject_column_names:
                continue
            missing_rate, n_available, dtype = _stats(rows, column)
            role = infer_role(column)
            records.append(
                FeatureRegistryRecord(
                    feature_name=column,
                    modality=modality,
                    source_file=str(path),
                    source_column=column,
                    role=role,
                    dtype=dtype,
                    description=f"{modality} variable {column}",
                    missing_rate=missing_rate,
                    n_available=n_available,
                    qc_dependency=[modality],
                    approved=False,
                    approval_reason="pending approval",
                )
            )
    return records


def write_feature_registry(records: list[FeatureRegistryRecord], path: Path) -> None:
    rows = [record.model_dump(mode="json") for record in records]
    write_csv(path, rows)
