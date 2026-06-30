from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from sleep_ai_scientist.schemas.foundation import ApprovedVariables, FeatureRegistryRecord, QCRecord


def build_foundation_report(
    config: dict[str, Any],
    subject_rows: list[dict[str, Any]],
    feature_records: list[FeatureRegistryRecord],
    qc_records: list[QCRecord],
    approved: ApprovedVariables,
    master_rows: list[dict[str, Any]],
    master_log: dict[str, Any],
) -> str:
    project_name = config.get("project", {}).get("name", "SleepAgent")
    group_counts = Counter(row.get("group", "") for row in subject_rows)
    modality_counts = {
        modality: sum(1 for row in subject_rows if str(row.get(f"has_{modality}", "")).lower() == "true")
        for modality in ["EEG", "fMRI", "DTI", "MRI", "scales"]
    }
    feature_counts = Counter(record.modality for record in feature_records)
    missing_top = sorted(feature_records, key=lambda item: item.missing_rate or 0, reverse=True)[:20]
    qc_counts = Counter(record.qc_status.value for record in qc_records)
    approved_payload = approved.model_dump(mode="json")
    approved_count = sum(len(values) for values in approved_payload.values())
    warnings = []
    for record in feature_records:
        if record.missing_rate is not None and record.missing_rate > 0.35:
            warnings.append(f"High missingness: {record.feature_name} ({record.missing_rate})")
    min_group = int(config.get("thresholds", {}).get("min_n_per_group", 1))
    for group, count in group_counts.items():
        if group and count < min_group:
            warnings.append(f"Small group size: {group} n={count}")
    if qc_counts.get("fail", 0):
        warnings.append(f"QC failures present: {qc_counts.get('fail', 0)} records")
    for key in ["age", "sex"]:
        if not any(record.feature_name == key for record in feature_records) and not any(key in row for row in subject_rows):
            warnings.append(f"Missing key covariate: {key}")

    lines = [
        "# Data Foundation Report",
        "",
        f"- Project: {project_name}",
        f"- Run time: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Inputs",
        "",
    ]
    for key, value in config.get("inputs", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Subjects", "", f"- Total subjects: {len(subject_rows)}"])
    for group in ["HC", "INS"]:
        lines.append(f"- {group}: {group_counts.get(group, 0)}")
    lines.extend(["", "## Modality Coverage", ""])
    for modality, count in modality_counts.items():
        lines.append(f"- {modality}: {count}")
    lines.extend(["", "## Feature Counts", ""])
    for modality, count in sorted(feature_counts.items()):
        lines.append(f"- {modality}: {count}")
    lines.extend(["", "## Highest Missingness Variables", ""])
    for record in missing_top:
        lines.append(f"- `{record.feature_name}` ({record.modality}): {record.missing_rate}")
    lines.extend(["", "## Approved Variables", "", f"- Total approved variables: {approved_count}"])
    for key, values in approved_payload.items():
        lines.append(f"- {key}: {len(values)}")
    lines.extend(["", "## QC Summary", ""])
    for status in ["pass", "caution", "fail", "unknown"]:
        lines.append(f"- {status}: {qc_counts.get(status, 0)}")
    lines.extend(
        [
            "",
            "## Multimodal Master Table",
            "",
            f"- Rows: {len(master_rows)}",
            f"- Columns: {len(master_rows[0]) if master_rows else 0}",
            f"- Input files: {master_log.get('input_file_count', 0)}",
            "",
            "## Knowledge Grounding Inputs",
            "",
            "- `data/foundation/subject_index.csv`",
            "- `data/foundation/feature_registry.csv`",
            "- `data/foundation/approved_variables.yaml`",
            "- `data/foundation/data_dictionary.yaml`",
            "- `data/foundation/qc_summary.csv`",
            "- `data/foundation/multimodal_master_table.csv`",
            "",
            "## Warnings",
            "",
        ]
    )
    lines.extend([f"- {warning}" for warning in warnings] or ["- None"])
    return "\n".join(lines) + "\n"


def write_foundation_report(path: Path, report: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
