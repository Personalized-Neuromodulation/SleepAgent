from tests.test_llm_evidence_verifier_mock import MockClient
from sleep_ai_scientist.grounding.evidence_extractor import extract_evidence
from sleep_ai_scientist.llm.evidence_verifier import EvidenceVerifier
from sleep_ai_scientist.schemas.evidence import EvidenceDirection
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_extractor_llm_mode_can_revise_candidate():
    paper = LiteratureRecord(paper_id="p1", title="Spindle", abstract="Spindle density showed no significant association.")
    config = {"evidence_extraction": {"llm_assist_enabled": True}}
    evidence = extract_evidence([paper], llm_verifier=EvidenceVerifier(MockClient()), llm_config=config)
    assert any(item.direction == EvidenceDirection.null and item.llm_verified for item in evidence)
