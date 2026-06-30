from sleep_ai_scientist.grounding.evidence_extractor import extract_evidence
from sleep_ai_scientist.grounding.evidence_grader import grade_evidence_records
from sleep_ai_scientist.grounding.literature_loader import load_literature


def test_grade_evidence_adds_nonuniform_scores():
    papers = load_literature("data/fixtures/toy_seed_papers.csv")
    graded = grade_evidence_records(extract_evidence(papers))
    scores = [item.evidence_quality_score for item in graded]
    assert all(score is not None and 0 <= score <= 1 for score in scores)
    assert len(set(scores)) > 1
