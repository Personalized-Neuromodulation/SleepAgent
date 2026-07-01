from sleep_ai_scientist.benchmark.grounding_benchmark import score_grounding


def test_grounding_detects_missing_variables_and_valid_evidence():
    hypothesis = {
        "hypothesis_id": "H1",
        "mechanism": "slow-wave generation",
        "used_data_features": ["missing_x", "ISI"],
        "supporting_evidence_ids": ["E1", "BAD"],
    }
    mapping = {"mappings": [{"concept": "slow-wave generation", "mapping_status": "mapped"}]}
    score = score_grounding(hypothesis, {"ISI"}, {"E1"}, mapping)
    assert score.missing_variables == ["missing_x"]
    assert score.evidence_ids == ["E1"]
    assert score.grounding_passed is False

