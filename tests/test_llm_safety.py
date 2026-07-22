from sleep_ai_scientist.llm.safety import validate_verified_claim


def test_llm_safety_rejects_missing_source_text():
    errors = validate_verified_claim({"claim": "claim", "direction": "support", "evidence_type": "empirical", "mechanism": "slow-wave generation"}, "")
    assert "missing_source_text" in errors
