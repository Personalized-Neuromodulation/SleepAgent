from sleep_ai_scientist.grounding.evidence_extractor import extract_evidence
from sleep_ai_scientist.schemas.evidence import EvidenceDirection
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_one_abstract_can_generate_multiple_evidence_and_null_direction():
    paper = LiteratureRecord(
        paper_id="p1",
        title="Insomnia EEG study",
        abstract="In insomnia patients, slow wave activity was reduced. Beta power was increased. Spindle density showed no significant association with insomnia.",
    )
    evidence = extract_evidence([paper])
    mechanisms = {item.mechanism for item in evidence}
    assert "slow-wave generation" in mechanisms
    assert "hyperarousal" in mechanisms
    assert "spindle generation" in mechanisms
    assert any(item.direction == EvidenceDirection.null for item in evidence)
    assert all(item.source_text for item in evidence)
    assert all(item.matched_terms for item in evidence)


def test_no_group_difference_not_support():
    paper = LiteratureRecord(paper_id="p2", title="Spindle study", abstract="There was no group difference in spindle density between insomnia and controls.")
    evidence = extract_evidence([paper])
    assert evidence
    assert all(item.direction != EvidenceDirection.support for item in evidence)
