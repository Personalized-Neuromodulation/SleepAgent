from sleep_ai_scientist.grounding.data_profile import build_analysis_ready_profile, build_observed_profile
from tests.config_helpers import toy_grounding_config


def test_build_profiles_from_fixtures():
    config = toy_grounding_config()
    observed = build_observed_profile(config)
    ready = build_analysis_ready_profile(config, observed)
    names = {item.feature_name for item in ready.features}
    assert "ISI" in names
    assert "slow_wave_density" in names
