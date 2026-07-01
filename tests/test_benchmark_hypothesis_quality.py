from sleep_ai_scientist.benchmark.hypothesis_quality import score_hypothesis_quality


def test_hypothesis_quality_valid_variables_score_high():
    hypothesis = {
        "hypothesis_id": "H1",
        "mechanism": "slow-wave generation",
        "variables": {"independent": ["slow_wave_density"], "dependent": ["ISI"], "covariates": []},
        "used_data_features": ["slow_wave_density", "ISI"],
        "supporting_evidence_ids": ["E1"],
        "falsification_criteria": ["No association."],
        "analysis_models": ["linear_model"],
        "evidence_level": "exploratory",
    }
    score = score_hypothesis_quality(hypothesis, {"slow_wave_density", "ISI"})
    assert score.valid_variables is True
    assert score.data_testability_score == 1.0


def test_hypothesis_quality_missing_variable_and_posthoc_warning():
    hypothesis = {
        "hypothesis_id": "H2",
        "title": "X causes insomnia",
        "primary_prediction": "X causes ISI.",
        "source": "posthoc_refinement",
        "evidence_level": "confirmatory",
        "variables": {"independent": ["missing_x"], "dependent": ["ISI"], "covariates": []},
        "used_data_features": ["missing_x", "ISI"],
    }
    score = score_hypothesis_quality(hypothesis, {"ISI"})
    assert score.valid_variables is False
    assert "posthoc_confirmatory_mislabel" in score.warnings
    assert "causal_language_risk" in score.warnings

