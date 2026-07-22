from sleep_ai_scientist.grounding.evidence_grader import grade_evidence
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord, EvidenceType


def test_scores_are_bounded_and_feasibility_depends_on_mappability():
    record = EvidenceRecord(
        evidence_id="e1",
        paper_id="p1",
        claim="claim",
        source_text="high impact molecular finding",
        matched_terms=["adenosine"],
        mechanism="adenosine_sleep_pressure",
        variable_or_feature="adenosine receptor",
        direction=EvidenceDirection.support,
        evidence_type=EvidenceType.empirical,
        data_mappability_hint="theory_only",
        journal_impact_factor=80.0,
        citation_count_age_normalized=100.0,
    )
    graded = grade_evidence(record)
    assert 0 <= graded.final_evidence_score <= 1
    assert graded.evidence_feasibility_score < 0.75
