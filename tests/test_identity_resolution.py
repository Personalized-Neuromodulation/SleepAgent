from sqlalchemy import select

from sleep_ai_scientist.literature.identity_resolution import resolve_and_upsert
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope
from sleep_ai_scientist.storage.models import Paper


def test_resolve_and_upsert_merges_non_ascii_title_canonical_duplicates(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "lit.db"))
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)

    with session_scope(engine) as session:
        canonical_id = "title:18aeaebcc9f6071f9d0cb1b8291a1ab59a5d1e2b"
        first = resolve_and_upsert(
            LiteratureRecord(
                paper_id=canonical_id,
                title="렘수면 행동 장애",
                year=2018,
                authors=["유수연"],
                provider="semantic_scholar",
                source="api:semantic_scholar",
            ),
            session,
            retrieval_channel="api_broad",
        )
        second = resolve_and_upsert(
            LiteratureRecord(
                paper_id=canonical_id,
                title="렘수면 행동 장애",
                year=2018,
                authors=["유수연"],
                provider="semantic_scholar",
                source="api:semantic_scholar",
            ),
            session,
            retrieval_channel="api_broad",
        )

        papers = list(session.scalars(select(Paper)))

    assert first.action == "inserted_new"
    assert second.action == "merged_into_existing"
    assert second.matched_by == "canonical_paper_id"
    assert len(papers) == 1
    assert papers[0].title == "렘수면 행동 장애"

    engine.dispose()
