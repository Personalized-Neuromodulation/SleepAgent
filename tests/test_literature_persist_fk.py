from sleep_ai_scientist.literature.library_builder import _persist_records
from sleep_ai_scientist.literature.query_loader import LiteratureQuery
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope
from sleep_ai_scientist.storage.repositories import PaperRepository, PaperSourceRepository


def test_persist_records_uses_stored_paper_id_for_duplicate_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "fk.db"))
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    query = LiteratureQuery(
        query_id="q1",
        query_text="sleep spindle",
        query_group="general_sleep_physiology",
        query_set_version="test_queries",
    )
    seed = LiteratureRecord(paper_id="seed_paper", title="Seed paper", doi="10.123/sleep", source="seed")
    api_duplicate = LiteratureRecord(
        paper_id="api_paper_duplicate",
        title="API duplicate",
        doi="10.123/sleep",
        source="api:openalex",
        provider="openalex",
        provider_id="OA1",
    )
    with session_scope(engine) as session:
        _persist_records(session, [seed, api_duplicate], [query], "test_queries")
        assert PaperRepository().count(session) == 1
        sources = PaperSourceRepository().list_sources_for_paper(session, "seed_paper")
        assert len(sources) == 2
        assert {source.paper_id for source in sources} == {"seed_paper"}
    engine.dispose()

