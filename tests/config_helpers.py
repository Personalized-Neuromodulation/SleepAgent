from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sleep_ai_scientist.common.config import load_config


TOY_FOUNDATION_INPUTS = {
    "subject_table": "data/fixtures/toy_subject_index.csv",
    "eeg_features": "data/fixtures/toy_eeg_features.csv",
    "fmri_features": "data/fixtures/toy_fmri_features.csv",
    "dti_features": "data/fixtures/toy_dti_features.csv",
    "mri_features": "data/fixtures/toy_mri_features.csv",
    "scale_features": "data/fixtures/toy_scale_features.csv",
    "qc_summary": "data/fixtures/toy_qc_summary.csv",
}


def toy_foundation_config() -> dict[str, Any]:
    config = load_config("configs/foundation_config.yaml")
    config.pop("foundation", None)
    config.setdefault("runtime", {})["allow_fixtures"] = True
    config.setdefault("paths", {})["fixture_dir"] = "data/fixtures"
    config["inputs"] = dict(TOY_FOUNDATION_INPUTS)
    return config


def toy_foundation_config_path(tmp_path: Path) -> Path:
    config = toy_foundation_config()
    config.pop("_config_path", None)
    config.pop("_project_root", None)
    config["outputs"].update(
        {
            "subject_index": str(tmp_path / "foundation" / "subject_index.csv"),
            "feature_registry": str(tmp_path / "foundation" / "feature_registry.csv"),
            "approved_variables": str(tmp_path / "foundation" / "approved_variables.yaml"),
            "data_dictionary": str(tmp_path / "foundation" / "data_dictionary.yaml"),
            "qc_summary": str(tmp_path / "foundation" / "qc_summary.csv"),
            "multimodal_master_table": str(tmp_path / "foundation" / "multimodal_master_table.csv"),
            "manifest": str(tmp_path / "foundation" / "foundation_manifest.json"),
            "report": str(tmp_path / "reports" / "phase0_foundation_report.md"),
        }
    )
    path = tmp_path / "toy_foundation_config.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def empty_foundation_config_path(tmp_path: Path) -> Path:
    config = load_config("configs/foundation_config.yaml")
    config.pop("_config_path", None)
    config.pop("_project_root", None)
    config["outputs"].update(
        {
            "subject_index": str(tmp_path / "foundation" / "subject_index.csv"),
            "feature_registry": str(tmp_path / "foundation" / "feature_registry.csv"),
            "approved_variables": str(tmp_path / "foundation" / "approved_variables.yaml"),
            "data_dictionary": str(tmp_path / "foundation" / "data_dictionary.yaml"),
            "qc_summary": str(tmp_path / "foundation" / "qc_summary.csv"),
            "multimodal_master_table": str(tmp_path / "foundation" / "multimodal_master_table.csv"),
            "manifest": str(tmp_path / "foundation" / "foundation_manifest.json"),
            "report": str(tmp_path / "reports" / "phase0_foundation_report.md"),
        }
    )
    path = tmp_path / "foundation_config.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def toy_grounding_config() -> dict[str, Any]:
    config = load_config("configs/grounding_config.yaml")
    config.setdefault("runtime", {})["allow_fixtures"] = True
    config["paths"].update(
        {
            "feature_registry": "data/fixtures/toy_feature_registry.csv",
            "approved_variables": "data/fixtures/toy_approved_variables.yaml",
            "multimodal_master_table": "data/fixtures/toy_multimodal_master_table.csv",
        }
    )
    return config
