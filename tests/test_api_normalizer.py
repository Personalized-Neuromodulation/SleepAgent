from sleep_ai_scientist.api.normalizer import deduplicate_api_records, make_api_record, normalize_title


def test_api_normalizer_deduplicates_doi_and_title():
    a = make_api_record("pubmed", "1", "Sleep EEG", doi="10.1/ABC", abstract="A")
    b = make_api_record("openalex", "2", "Sleep EEG", doi="https://doi.org/10.1/abc", abstract="B")
    c = make_api_record("semantic_scholar", "3", "Sleep, EEG!", abstract="C")
    d = make_api_record("europe_pmc", "4", "sleep eeg", abstract="D")
    merged = deduplicate_api_records([a, b, c, d])
    assert len(merged) == 2
    assert normalize_title("Sleep,  EEG!") == "sleep eeg"
    assert "pubmed" in merged[0].source

