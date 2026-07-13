from sqlalchemy import select

from sleep_ai_scientist.literature.identity_resolution import build_deduplication_summary, resolve_and_upsert
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope
from sleep_ai_scientist.storage.models import DeduplicationEvent, Paper, PaperSource


def test_api_broad_and_journal_targeted_doi_overlap_merges(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "lit.db"))
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    with session_scope(engine) as session:
        resolve_and_upsert(
            LiteratureRecord(paper_id="api1", title="Sleep apnea trial", doi="10.1/sleep", provider="pubmed", abstract="long abstract"),
            session,
            retrieval_channel="api_broad",
        )
        resolve_and_upsert(
            LiteratureRecord(
                paper_id="target1",
                title="Sleep apnea trial",
                doi="https://doi.org/10.1/SLEEP",
                provider="crossref",
                journal_priority_score=9.0,
            ),
            session,
            retrieval_channel="journal_targeted",
        )

        papers = list(session.scalars(select(Paper)))
        sources = list(session.scalars(select(PaperSource)))
        events = list(session.scalars(select(DeduplicationEvent)))
        summary = build_deduplication_summary(session)

        assert len(papers) == 1
        assert papers[0].paper_id == "doi:10.1/sleep"
        assert papers[0].retrieval_channels_json == ["api_broad", "journal_targeted"]
        assert papers[0].source_providers_json == ["crossref", "pubmed"]
        assert papers[0].journal_priority_score == 9.0
        assert len(sources) == 2
        assert {source.retrieval_channel for source in sources} == {"api_broad", "journal_targeted"}
        assert any(event.action == "merged_into_existing" and event.matched_by == "doi" for event in events)
        assert summary["overlap_api_broad_and_journal_targeted"] == 1
    engine.dispose()

