from sleep_ai_scientist.literature.query_expansion import generate_query_expansion_candidates
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_query_expansion_no_duplicate_query():
    records = [LiteratureRecord(paper_id="p1", title="Orexin optogenetic sleep arousal", abstract="Orexin optogenetic neurons regulate sleep wake.")]
    candidates = generate_query_expansion_candidates(records, ["orexin optogenetic sleep"])
    queries = [item["candidate_query"] for item in candidates]
    assert len(queries) == len(set(queries))
    assert "orexin optogenetic sleep" not in queries

