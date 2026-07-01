from pathlib import Path

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.hypothesis.generator import generate_candidate_hypotheses


def test_hypothesis_generator_uses_only_analysis_ready_variables():
    config = load_config("configs/hypothesis_config.yaml")
    profile = read_yaml(Path(config["_project_root"]) / "outputs/profiles/analysis_ready_profile.yaml")
    allowed = {item["feature_name"] for item in profile["features"]} | {"group"}
    hypotheses = generate_candidate_hypotheses(config)
    assert hypotheses
    for hypothesis in hypotheses:
        assert set(hypothesis.used_data_features) <= allowed
