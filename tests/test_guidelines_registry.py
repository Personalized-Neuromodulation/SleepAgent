from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.knowledge_sources.guidelines import build_guideline_records


def test_guidelines_registry_metadata_only():
    records = build_guideline_records(load_config("configs/knowledge_sources_config.yaml"))
    assert records
    assert all(record["access_status"] == "metadata_only" for record in records)
    assert all("restricted" not in (record["recommendation_summary"].lower()) for record in records)

