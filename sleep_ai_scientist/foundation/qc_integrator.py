from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_csv
from sleep_ai_scientist.foundation.utils import input_path, normalize_subject_rows
from sleep_ai_scientist.schemas.foundation import QCRecord, QCStatus


def normalize_qc_status(value: str, config: dict[str, Any]) -> QCStatus:
    raw = str(value or "").strip()
    qc_cfg = config.get("qc", {})
    if raw in {str(item) for item in qc_cfg.get("pass_values", [])}:
        return QCStatus.pass_
    if raw in {str(item) for item in qc_cfg.get("caution_values", [])}:
        return QCStatus.caution
    if raw in {str(item) for item in qc_cfg.get("fail_values", [])}:
        return QCStatus.fail
    return QCStatus.unknown


def load_qc_records(config: dict[str, Any], subject_ids: list[str] | None = None) -> list[QCRecord]:
    path = input_path(config, "qc_summary")
    if not path.exists():
        return [
            QCRecord(subject_id=subject_id, modality="all", qc_status=QCStatus.unknown, reason="QC file missing")
            for subject_id in (subject_ids or [])
        ]
    from sleep_ai_scientist.common.io import read_csv

    rows = normalize_subject_rows(read_csv(path), config)
    records = []
    for row in rows:
        records.append(
            QCRecord(
                subject_id=row.get("subject_id", ""),
                modality=row.get("modality", "all"),
                qc_status=normalize_qc_status(row.get("qc_status", ""), config),
                qc_metric=row.get("qc_metric") or None,
                qc_value=row.get("qc_value") or None,
                reason=row.get("reason") or None,
            )
        )
    return records


def overall_qc_by_subject(records: list[QCRecord]) -> dict[str, str]:
    by_subject: dict[str, list[str]] = defaultdict(list)
    for record in records:
        by_subject[record.subject_id].append(record.qc_status.value)
    result = {}
    for subject_id, statuses in by_subject.items():
        if "fail" in statuses:
            result[subject_id] = "fail"
        elif "caution" in statuses:
            result[subject_id] = "caution"
        elif "pass" in statuses:
            result[subject_id] = "pass"
        else:
            result[subject_id] = "unknown"
    return result


def qc_counts(records: list[QCRecord]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        counts[record.modality][record.qc_status.value] += 1
    return {modality: dict(counter) for modality, counter in counts.items()}


def write_qc_summary(records: list[QCRecord], path: Path) -> None:
    write_csv(path, [record.model_dump(mode="json") for record in records])
