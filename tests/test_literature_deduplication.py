from sleep_ai_scientist.grounding.literature_registry import merge_literature_registry
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_api_metadata_merges_during_literature_merge():
    first = LiteratureRecord(paper_id="api1", title="API title", abstract="", doi="10.1/a", source="api:pubmed", keywords=["insomnia"])
    second = LiteratureRecord(paper_id="api2", title="API title duplicate", abstract="api abstract", doi="10.1/a", source="api:openalex", keywords=["EEG"])

    merged, report = merge_literature_registry([first, second])

    assert len(merged) == 1
    assert merged[0].paper_id == "api1"
    assert merged[0].abstract == "api abstract"
    assert "api:pubmed" in merged[0].source
    assert "api:openalex" in merged[0].source
    assert sorted(merged[0].keywords) == ["EEG", "insomnia"]
