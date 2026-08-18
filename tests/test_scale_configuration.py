from __future__ import annotations

import tomllib
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCEDATA_ROOT = "/data/fmri_agent/multimodal_sleep_data/bids/sourcedata"


def test_default_experiment_config_enables_scale_xlsx_input() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "configs/experiment_config.yaml").read_text(encoding="utf-8"))

    assert config["feature_extraction"]["scales"]["input_root"] == SOURCEDATA_ROOT


def test_project_manifests_declare_openpyxl() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    environment = yaml.safe_load((PROJECT_ROOT / "environment.yml").read_text(encoding="utf-8"))
    project_dependencies = project["project"]["dependencies"]
    pip_dependencies = next(item["pip"] for item in environment["dependencies"] if isinstance(item, dict))

    assert "openpyxl>=3.1" in project_dependencies
    assert "openpyxl>=3.1" in pip_dependencies
