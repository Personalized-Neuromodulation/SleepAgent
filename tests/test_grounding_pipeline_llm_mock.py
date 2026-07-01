from sleep_ai_scientist.grounding.evidence_extractor import extract_evidence
from sleep_ai_scientist.llm.evidence_verifier import EvidenceVerifier
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from tests.test_llm_evidence_verifier_mock import MockClient


def test_grounding_pipeline_llm_mock_extraction_path():
    paper = LiteratureRecord(paper_id="p1", title="Spindle", abstract="Spindle density showed no significant association.")
    evidence = extract_evidence([paper], llm_verifier=EvidenceVerifier(MockClient()), llm_config={"evidence_extraction": {"llm_assist_enabled": True}})
    assert any(item.llm_verified for item in evidence)
