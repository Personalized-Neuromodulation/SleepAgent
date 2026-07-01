from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.knowledge_sources.standards import build_standard_records


def test_standards_registry_does_not_download_restricted_content():
    records = build_standard_records(load_config("configs/knowledge_sources_config.yaml"))
    assert records
    assert any(record["rule_category"] == "sleep_staging" for record in records)
    assert all("metadata" in record["rule_summary"].lower() for record in records)

