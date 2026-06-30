from pathlib import Path

from sleep_ai_scientist.foundation.foundation_pipeline import run_foundation_pipeline


def test_foundation_pipeline_generates_outputs():
    result = run_foundation_pipeline("configs/foundation_config.yaml")
    assert result["subject_count"] == 5
    required = [
        "data/foundation/subject_index.csv",
        "data/foundation/feature_registry.csv",
        "data/foundation/approved_variables.yaml",
        "data/foundation/data_dictionary.yaml",
        "data/foundation/qc_summary.csv",
        "data/foundation/multimodal_master_table.csv",
        "reports/data_foundation_report.md",
    ]
    for path in required:
        assert Path(path).exists()
