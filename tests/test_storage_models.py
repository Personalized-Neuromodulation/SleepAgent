from sleep_ai_scientist.storage.models import Base


def test_storage_models_include_required_tables():
    tables = set(Base.metadata.tables)
    assert {"papers", "paper_sources", "queries", "query_results", "corpus_versions", "build_runs", "checkpoints", "audit_reports", "error_logs"} <= tables

