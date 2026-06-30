from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.grounding.data_profile import build_analysis_ready_profile, build_observed_profile


def test_build_profiles_from_fixtures():
    config = load_config("configs/grounding_config.yaml")
    observed = build_observed_profile(config)
    ready = build_analysis_ready_profile(config, observed)
    names = {item.feature_name for item in ready.features}
    assert "ISI" in names
    assert "slow_wave_density" in names
