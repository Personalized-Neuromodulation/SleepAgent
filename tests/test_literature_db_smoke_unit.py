import pytest

from sleep_ai_scientist.literature_db.engine import create_database_engine
from sleep_ai_scientist.literature_db.smoke_test import BASE_QUERY, PROVIDERS, provider_query


def test_smoke_query_semantics_and_per_provider_queries():
    assert "sleep deprivation" in BASE_QUERY
    assert "functional connectivity" in BASE_QUERY
    queries={provider:provider_query(provider,2026) for provider in PROVIDERS}
    assert set(queries)=={"pubmed","europe_pmc","openalex","semantic_scholar"}
    assert all("2016" in query and "2026" in query for query in queries.values())


def test_postgresql_required_rejects_alternative_url():
    with pytest.raises(ValueError,match="requires PostgreSQL"):
        create_database_engine("configs/literature_database_test.yaml",url="mysql://user:password@localhost/test",require_postgresql=True)
