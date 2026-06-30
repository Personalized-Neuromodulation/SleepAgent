from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_yaml
from sleep_ai_scientist.schemas.foundation import ApprovedVariables, FeatureRegistryRecord


def approve_feature(record: FeatureRegistryRecord, config: dict[str, Any]) -> tuple[bool, str]:
    thresholds = config.get("thresholds", {})
    role = record.role.value if hasattr(record.role, "value") else str(record.role)
    max_missing = float(thresholds.get("max_missing_rate_primary" if role in {"outcome", "group"} else "max_missing_rate_secondary", 0.35))
    min_n = int(thresholds.get("min_n_total", 1))
    if record.missing_rate is not None and record.missing_rate > max_missing:
        return False, f"missing_rate>{max_missing}"
    if record.n_available is not None and record.n_available < min_n:
        return False, f"n_available<{min_n}"
    return True, "passes missingness and sample-size thresholds"


def build_approved_variables(records: list[FeatureRegistryRecord], config: dict[str, Any]) -> tuple[ApprovedVariables, list[FeatureRegistryRecord]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    updated: list[FeatureRegistryRecord] = []
    for record in records:
        approved, reason = approve_feature(record, config)
        record.approved = approved
        record.approval_reason = reason
        updated.append(record)
        if not approved:
            continue
        role = record.role.value if hasattr(record.role, "value") else str(record.role)
        if role == "covariate":
            buckets["covariates"].append(record.feature_name)
        elif role == "group":
            buckets["group"].append(record.feature_name)
        elif role == "qc":
            buckets["qc"].append(record.feature_name)
        elif record.modality in {"EEG", "fMRI", "DTI", "MRI"}:
            buckets[record.modality].append(record.feature_name)
        elif record.modality == "scales":
            buckets["scales"].append(record.feature_name)
    approved_variables = ApprovedVariables(
        EEG=sorted(set(buckets["EEG"])),
        fMRI=sorted(set(buckets["fMRI"])),
        DTI=sorted(set(buckets["DTI"])),
        MRI=sorted(set(buckets["MRI"])),
        scales=sorted(set(buckets["scales"])),
        covariates=sorted(set(buckets["covariates"])),
        group=sorted(set(buckets["group"])),
        qc=sorted(set(buckets["qc"])),
    )
    return approved_variables, updated


def write_approved_variables(approved: ApprovedVariables, path: Path) -> None:
    write_yaml(path, approved.model_dump(mode="json"))
