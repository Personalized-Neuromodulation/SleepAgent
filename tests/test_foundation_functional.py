from pathlib import Path

from sleep_ai_scientist.common.io import read_csv, read_yaml
from sleep_ai_scientist.foundation.foundation_pipeline import run_foundation_pipeline
from tests.config_helpers import toy_foundation_config_path


def test_foundation_functional_outputs_and_raw_unchanged(tmp_path):
    raw_dir = Path("data/raw")
    before = sorted(str(path) for path in raw_dir.rglob("*")) if raw_dir.exists() else []
    result = run_foundation_pipeline(toy_foundation_config_path(tmp_path))
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
        assert Path(path).exists(), path
    master = read_csv(tmp_path / "foundation" / "multimodal_master_table.csv")
    columns = set(master[0])
    for column in ["subject_id", "group", "slow_wave_density", "thalamus_DMN_FC", "thalamic_radiation_FA", "thalamus_volume", "ISI", "PSQI"]:
        assert column in columns
    registry_vars = {row["feature_name"] for row in read_csv(tmp_path / "foundation" / "feature_registry.csv")}
    approved = read_yaml(tmp_path / "foundation" / "approved_variables.yaml")
    approved_values = {item for values in approved.values() if isinstance(values, list) for item in values}
    assert approved_values <= registry_vars | {"group"}
    after = sorted(str(path) for path in raw_dir.rglob("*")) if raw_dir.exists() else []
    assert before == after
    assert result["subject_count"] > 0
