from sleep_ai_scientist.experiment.critic import review_experiment


def test_critic_defaults_to_no_causal_language():
    plan = {"experiment_id": "EXP_TEST", "hypothesis_id": "H_TEST", "predictors": ["x"], "covariates": [], "quality_gates": {"min_n_total": 2}}
    result = {"status": "ok", "n_used": 3, "effect_sizes": {"x": 0.2}, "corrected_p_values": {"x": 0.5}}
    robustness = {"passed": True, "warnings": []}
    review = review_experiment(None, plan, result, robustness, {})
    assert review.causal_language_allowed is False
    assert review.decision == "rejected"

