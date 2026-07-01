from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.hypothesis.reflection import reflect_hypothesis
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, HypothesisVariables


def test_reflection_rejects_unsupported_or_causal_hypothesis():
    config = load_config("configs/co_scientist_config.yaml")
    hypothesis = HypothesisRecord(
        hypothesis_id="H_BAD",
        title="Imaginary biomarker causes insomnia",
        mechanism="unsupported",
        primary_prediction="imaginary_feature causes ISI change.",
        variables=HypothesisVariables(independent=["imaginary_feature"], dependent=["ISI"], covariates=[]),
        used_data_features=["imaginary_feature", "ISI"],
        falsification_criteria=[],
        supporting_evidence_ids=[],
    )
    review = reflect_hypothesis(hypothesis, config)
    assert review.unsupported_variables == ["imaginary_feature"]
    assert review.causal_language_risk is True
    assert review.falsifiability_score < 0.5
    assert review.recommendation == "reject"

