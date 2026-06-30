from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.foundation.approved_variables import build_approved_variables
from sleep_ai_scientist.foundation.feature_registry import scan_feature_tables


def test_approved_variables_thresholds_and_no_fabrication():
    config = load_config("configs/foundation_config.yaml")
    approved, records = build_approved_variables(scan_feature_tables(config), config)
    payload = approved.model_dump(mode="json")
    assert "slow_wave_density" in payload["EEG"]
    assert "thalamus_DMN_FC" in payload["fMRI"]
    assert "nonexistent_variable" not in payload["EEG"]
    assert all(record.approval_reason for record in records)
