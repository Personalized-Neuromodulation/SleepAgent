from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.knowledge_sources.diagnostic_taxonomy import build_diagnostic_terms


def test_diagnostic_taxonomy_curated_no_icsd_fulltext():
    records = build_diagnostic_terms(load_config("configs/knowledge_sources_config.yaml"))
    categories = {record["category"] for record in records}
    assert "insomnia_disorders" in categories
    assert all("No restricted ICSD text copied." == record["notes"] for record in records)

