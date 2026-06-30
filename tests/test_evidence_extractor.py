from sleep_ai_scientist.grounding.evidence_extractor import extract_evidence
from sleep_ai_scientist.grounding.literature_loader import load_literature


def test_extract_evidence_from_fixture():
    papers = load_literature("data/fixtures/toy_seed_papers.csv")
    evidence = extract_evidence(papers)
    mechanisms = {item.mechanism for item in evidence}
    assert "thalamocortical coupling" in mechanisms
    assert "slow-wave generation" in mechanisms
    assert any(item.variable_or_feature == "ISI" for item in evidence)
