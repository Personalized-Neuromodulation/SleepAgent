from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.common.io import write_csv, write_json, write_yaml
from sleep_ai_scientist.foundation.approved_variables import build_approved_variables, write_approved_variables
from sleep_ai_scientist.foundation.data_dictionary import build_data_dictionary, write_data_dictionary
from sleep_ai_scientist.foundation.feature_registry import scan_feature_tables, write_feature_registry
from sleep_ai_scientist.foundation.foundation_report import build_foundation_report, write_foundation_report
from sleep_ai_scientist.foundation.master_table import build_multimodal_master_table, write_master_table
from sleep_ai_scientist.foundation.qc_integrator import load_qc_records, write_qc_summary
from sleep_ai_scientist.foundation.subject_index import build_subject_index, write_subject_index
from sleep_ai_scientist.foundation.utils import output_path


EMPTY_SUBJECT_FIELDS = [
    "subject_id",
    "group",
    "age",
    "sex",
    "has_EEG",
    "has_fMRI",
    "has_DTI",
    "has_MRI",
    "has_scales",
    "available_modalities",
    "overall_qc_status",
    "notes",
]

EMPTY_FEATURE_FIELDS = [
    "feature_name",
    "modality",
    "source_file",
    "source_column",
    "role",
    "dtype",
    "unit",
    "description",
    "missing_rate",
    "n_available",
    "qc_dependency",
    "approved",
    "approval_reason",
]

EMPTY_QC_FIELDS = ["subject_id", "modality", "qc_status", "qc_metric", "qc_value", "reason"]


def _is_no_real_data_mode(config: dict[str, Any]) -> bool:
    return str(config.get("foundation", {}).get("mode", "")).strip().lower() == "no_real_data"


def _write_no_real_data_foundation(config: dict[str, Any]) -> dict[str, Any]:
    for key in ["subject_index", "feature_registry", "approved_variables", "data_dictionary", "qc_summary", "multimodal_master_table", "report"]:
        output_path(config, key).parent.mkdir(parents=True, exist_ok=True)

    write_csv(output_path(config, "subject_index"), [], fieldnames=EMPTY_SUBJECT_FIELDS)
    write_csv(output_path(config, "feature_registry"), [], fieldnames=EMPTY_FEATURE_FIELDS)
    write_yaml(
        output_path(config, "approved_variables"),
        {
            "EEG": [],
            "fMRI": [],
            "DTI": [],
            "MRI": [],
            "scales": [],
            "covariates": [],
            "group": [],
            "qc": [],
        },
    )
    write_yaml(output_path(config, "data_dictionary"), {"variables": []})
    write_csv(output_path(config, "qc_summary"), [], fieldnames=EMPTY_QC_FIELDS)
    write_csv(output_path(config, "multimodal_master_table"), [], fieldnames=["subject_id"])

    manifest = {
        "foundation_mode": "no_real_data",
        "real_subject_data_available": False,
        "feature_values_available": False,
        "description": "Pre-experiment foundation: no subject-level raw or derived feature values are registered.",
        "expected_next_step": "grounding builds literature evidence and a theoretical mechanism graph; experiment later selects real modalities and extracts features.",
        "outputs": {
            key: str(output_path(config, key))
            for key in ["subject_index", "feature_registry", "approved_variables", "data_dictionary", "qc_summary", "multimodal_master_table"]
        },
    }
    manifest_path = output_path(config, "manifest") if "manifest" in config.get("outputs", {}) else output_path(config, "subject_index").parent / "foundation_manifest.json"
    write_json(manifest_path, manifest)

    report = "\n".join(
        [
            "# Data Foundation Report",
            "",
            "## Mode",
            "",
            "- foundation_mode: `no_real_data`",
            "- real_subject_data_available: `false`",
            "- feature_values_available: `false`",
            "",
            "This foundation intentionally contains no subject-level feature values.",
            "It is suitable for pre-experiment grounding, literature evidence extraction, and theoretical mechanism graph construction.",
        ]
    )
    write_foundation_report(output_path(config, "report"), report)
    return {
        "mode": "no_real_data",
        "subject_count": 0,
        "feature_count": 0,
        "qc_record_count": 0,
        "master_rows": 0,
        "master_columns": 1,
        "manifest": str(manifest_path),
        "outputs": {
            key: str(output_path(config, key))
            for key in ["subject_index", "feature_registry", "approved_variables", "data_dictionary", "qc_summary", "multimodal_master_table", "report"]
        },
    }


def run_foundation_pipeline(config_path_value: str | Path) -> dict[str, Any]:
    config = load_config(config_path_value)
    if _is_no_real_data_mode(config):
        return _write_no_real_data_foundation(config)

    for key in ["subject_index", "feature_registry", "approved_variables", "data_dictionary", "qc_summary", "multimodal_master_table", "report"]:
        output_path(config, key).parent.mkdir(parents=True, exist_ok=True)

    qc_records = load_qc_records(config)
    subject_rows = build_subject_index(config, qc_records)
    write_subject_index(subject_rows, output_path(config, "subject_index"))

    if not qc_records:
        qc_records = load_qc_records(config, [row["subject_id"] for row in subject_rows])
    write_qc_summary(qc_records, output_path(config, "qc_summary"))

    feature_records = scan_feature_tables(config)
    approved, feature_records = build_approved_variables(feature_records, config)
    write_feature_registry(feature_records, output_path(config, "feature_registry"))
    write_approved_variables(approved, output_path(config, "approved_variables"))

    dictionary_entries = build_data_dictionary(feature_records)
    write_data_dictionary(dictionary_entries, output_path(config, "data_dictionary"))

    master_rows, master_log = build_multimodal_master_table(config, subject_rows)
    write_master_table(master_rows, output_path(config, "multimodal_master_table"))

    report = build_foundation_report(config, subject_rows, feature_records, qc_records, approved, master_rows, master_log)
    write_foundation_report(output_path(config, "report"), report)

    return {
        "subject_count": len(subject_rows),
        "feature_count": len(feature_records),
        "qc_record_count": len(qc_records),
        "master_rows": len(master_rows),
        "master_columns": len(master_rows[0]) if master_rows else 0,
        "outputs": {
            key: str(output_path(config, key))
            for key in ["subject_index", "feature_registry", "approved_variables", "data_dictionary", "qc_summary", "multimodal_master_table", "report"]
        },
    }


def generate_foundation_report(config_path_value: str | Path) -> dict[str, Any]:
    return run_foundation_pipeline(config_path_value)
