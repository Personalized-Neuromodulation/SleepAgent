from sleep_ai_scientist.grounding.literature_registry import merge_literature_registry
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_seed_metadata_wins_during_literature_merge():
    seed = LiteratureRecord(paper_id="seed1", title="Seed title", abstract="manual", doi="10.1/a", source="seed", notes="curated")
    api = LiteratureRecord(paper_id="api1", title="API title", abstract="api", doi="10.1/a", source="api:pubmed", notes="provider=pubmed")

    merged, report = merge_literature_registry([seed], [api])

    assert len(merged) == 1
    assert merged[0].paper_id == "seed1"
    assert merged[0].title == "Seed title"
    assert "api:pubmed" in merged[0].source
    assert report[0]["seed_priority_used"] is True
