import json

from sleep_ai_scientist.literature.identity_resolution import resolve_and_upsert
from sleep_ai_scientist.literature.rag_indexer import build_rag_index
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope


def test_rag_index_writes_one_abstract_chunk_per_canonical_paper(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "lit.db"))
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    with session_scope(engine) as session:
        resolve_and_upsert(
            LiteratureRecord(paper_id="a", title="Sleep abstract", doi="10.1/a", abstract="An abstract.", provider="pubmed", journal_priority_score=7.0),
            session,
            retrieval_channel="api_broad",
        )
        resolve_and_upsert(
            LiteratureRecord(paper_id="b", title="Sleep abstract", doi="10.1/a", abstract="An abstract.", provider="crossref"),
            session,
            retrieval_channel="journal_targeted",
        )
        result = build_rag_index(session, tmp_path / "rag.jsonl")

        rows = [json.loads(line) for line in (tmp_path / "rag.jsonl").read_text(encoding="utf-8").splitlines()]
        assert result["chunk_count"] == 1
        assert rows[0]["chunk_id"] == "abstract:doi:10.1/a"
        assert rows[0]["metadata"]["retrieval_channels"] == ["api_broad", "journal_targeted"]
        assert rows[0]["metadata"]["journal_priority_score"] == 7.0
    engine.dispose()
