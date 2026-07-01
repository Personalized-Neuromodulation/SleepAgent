from sleep_ai_scientist.api.normalizer import make_api_record


def test_citation_count_age_normalized_calculated():
    record = make_api_record("openalex", "id1", "Title", year=2025, citation_count=20)
    assert record.citation_source == "openalex"
    assert record.citation_count_age_normalized is not None
    assert record.citation_count_age_normalized > 0
