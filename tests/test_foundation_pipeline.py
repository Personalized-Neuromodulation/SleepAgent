from pathlib import Path

from sleep_ai_scientist.common.io import read_csv
from sleep_ai_scientist.foundation.foundation_pipeline import run_foundation_pipeline
from tests.config_helpers import empty_foundation_config_path, toy_foundation_config_path


def test_foundation_pipeline_default_config_is_empty_foundation(tmp_path):
    result = run_foundation_pipeline(empty_foundation_config_path(tmp_path))
    assert result["mode"] == "empty_foundation"
    assert result["subject_count"] == 0
    assert result["feature_count"] == 0
    assert read_csv(tmp_path / "foundation" / "subject_index.csv") == []


def test_foundation_pipeline_can_still_run_toy_fixture_config(tmp_path):
    result = run_foundation_pipeline(toy_foundation_config_path(tmp_path))
    assert result["subject_count"] == 5
    required = [
        tmp_path / "foundation" / "subject_index.csv",
        tmp_path / "foundation" / "feature_registry.csv",
        tmp_path / "foundation" / "approved_variables.yaml",
        tmp_path / "foundation" / "data_dictionary.yaml",
        tmp_path / "foundation" / "qc_summary.csv",
        tmp_path / "foundation" / "multimodal_master_table.csv",
        tmp_path / "reports" / "phase0_foundation_report.md",
    ]
    for path in required:
        assert Path(path).exists()
