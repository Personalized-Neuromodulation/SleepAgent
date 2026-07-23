from sleep_ai_scientist.foundation.feature_registry import scan_feature_tables
from tests.config_helpers import toy_foundation_config


def test_feature_registry_scans_tables_and_roles():
    config = toy_foundation_config()
    records = scan_feature_tables(config)
    by_name = {record.feature_name: record for record in records}
    assert by_name["slow_wave_density"].modality == "EEG"
    assert by_name["ISI"].role.value == "outcome"
    assert by_name["mean_FD"].role.value == "covariate"
    assert by_name["slow_wave_density"].missing_rate == 0.2
