from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope
from sleep_ai_scientist.storage.repositories import PaperRepository, QueryRepository


def test_repositories_upsert_paper_and_query(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "repo.db"))
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    with session_scope(engine) as session:
        paper_repo = PaperRepository()
        paper_repo.upsert_paper(session, LiteratureRecord(paper_id="p1", title="Sleep spindle EEG", doi="10.1/a"))
        paper_repo.upsert_paper(session, LiteratureRecord(paper_id="p1", title="Sleep spindle EEG updated", doi="10.1/a", journal="Sleep"))
        assert paper_repo.count(session) == 1
        assert paper_repo.get_by_doi(session, "10.1/a").journal == "Sleep"
        query = QueryRepository().upsert_query(session, "sleep spindle", "general_sleep_physiology", "v1")
        assert query.query_id
    engine.dispose()

