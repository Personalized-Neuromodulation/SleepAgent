from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.literature.deduplication import deduplicate_records


def test_literature_registry_deduplicates_by_doi():
    records = [
        LiteratureRecord(paper_id="api1", title="Sleep", doi="10.1/sleep", source="api:pubmed"),
        LiteratureRecord(paper_id="api1", title="Sleep duplicate", doi="10.1/sleep", source="api:openalex"),
    ]
    merged, report = deduplicate_records(records)
    assert len(merged) == 1
    assert merged[0].paper_id == "api1"
    assert report[0]["match_type"] == "doi"
