from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.foundation.feature_registry import infer_role, scan_feature_tables


def test_feature_registry_scans_tables_and_roles():
    config = load_config("configs/foundation_config.yaml")
    records = scan_feature_tables(config)
    by_name = {record.feature_name: record for record in records}
    assert by_name["slow_wave_density"].modality == "EEG"
    assert by_name["ISI"].role.value == "outcome"
    assert by_name["mean_FD"].role.value == "covariate"
    assert by_name["slow_wave_density"].missing_rate == 0.2
