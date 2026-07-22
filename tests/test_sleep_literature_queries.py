from sleep_ai_scientist.literature.query_loader import load_query_set


def test_sleep_literature_queries_cover_broad_sleep_science():
    payload, queries = load_query_set("configs/sleep_literature_queries.yaml")
    groups = set(payload["queries"])
    assert "general_sleep_physiology" in groups
    assert "animal_causal_sleep" in groups
    assert "molecular_cellular_sleep" in groups
    assert "human_sleep_neuroimaging" in groups
    assert "insomnia_clinical_application" in groups
    assert len(queries) >= 100

