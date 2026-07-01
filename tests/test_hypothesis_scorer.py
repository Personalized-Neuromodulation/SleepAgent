from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.hypothesis.generator import generate_candidate_hypotheses
from sleep_ai_scientist.hypothesis.scorer import score_hypothesis


def test_hypothesis_scorer_is_pre_analysis_only():
    config = load_config("configs/hypothesis_config.yaml")
    hypothesis = generate_candidate_hypotheses(config)[0]
    scored = score_hypothesis(hypothesis, config)
    assert scored.pre_analysis_score is not None
    assert "evidence_strength" in scored.score_components
    assert all("p_value" not in key for key in scored.score_components)

