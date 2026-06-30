from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_csv, write_csv
from sleep_ai_scientist.foundation.qc_integrator import overall_qc_by_subject
from sleep_ai_scientist.foundation.utils import input_path, normalize_subject_rows, subject_column
from sleep_ai_scientist.schemas.foundation import QCRecord, SubjectRecord


FEATURE_INPUTS = {
    "EEG": "eeg_features",
    "fMRI": "fmri_features",
    "DTI": "dti_features",
    "MRI": "mri_features",
    "scales": "scale_features",
}


def load_subject_rows(config: dict[str, Any]) -> list[dict[str, str]]:
    path = input_path(config, "subject_table")
    if path.exists():
        return normalize_subject_rows(read_csv(path), config)
    for key in FEATURE_INPUTS.values():
        feature_path = input_path(config, key)
        if feature_path.exists():
            return normalize_subject_rows(read_csv(feature_path), config)
    return []


def modality_subjects(config: dict[str, Any]) -> dict[str, set[str]]:
    coverage: dict[str, set[str]] = {}
    for modality, key in FEATURE_INPUTS.items():
        path = input_path(config, key)
        if path.exists():
            rows = normalize_subject_rows(read_csv(path), config)
            coverage[modality] = {row["subject_id"] for row in rows}
        else:
            coverage[modality] = set()
    return coverage


def build_subject_index(config: dict[str, Any], qc_records: list[QCRecord]) -> list[dict[str, Any]]:
    rows = load_subject_rows(config)
    coverage = modality_subjects(config)
    qc_status = overall_qc_by_subject(qc_records)
    output = []
    for row in rows:
        subject_id = row["subject_id"]
        available = [modality for modality, subjects in coverage.items() if subject_id in subjects]
        record = SubjectRecord(
            subject_id=subject_id,
            group=row.get("group") or None,
            age=float(row["age"]) if row.get("age") else None,
            sex=row.get("sex") or None,
            available_modalities=available,
            qc_status=qc_status.get(subject_id, "unknown"),
            notes=row.get("notes") or None,
        )
        item = {
            "subject_id": record.subject_id,
            "group": record.group or "",
            "age": record.age if record.age is not None else "",
            "sex": record.sex or "",
            "has_EEG": "EEG" in available,
            "has_fMRI": "fMRI" in available,
            "has_DTI": "DTI" in available,
            "has_MRI": "MRI" in available,
            "has_scales": "scales" in available,
            "available_modalities": ";".join(available),
            "overall_qc_status": record.qc_status or "unknown",
            "notes": record.notes or "",
        }
        output.append(item)
    return output


def write_subject_index(rows: list[dict[str, Any]], path: Path) -> None:
    write_csv(path, rows)
