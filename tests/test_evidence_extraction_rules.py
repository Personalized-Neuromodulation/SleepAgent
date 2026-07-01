from sleep_ai_scientist.grounding.evidence_extractor import load_evidence_rules


def test_evidence_rules_include_human_and_animal_mechanisms():
    rules = load_evidence_rules("configs/evidence_extraction_rules.yaml")
    assert "slow-wave generation" in rules["mechanisms"]
    assert "orexin_hypocretin_arousal" in rules["mechanisms"]
    assert "mouse" in rules["animal_terms"]["species"]
    assert "null" in rules["direction_terms"]
