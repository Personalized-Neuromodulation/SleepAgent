import json

from sleep_ai_scientist.literature.identity_resolution import resolve_and_upsert
from sleep_ai_scientist.literature.rag_indexer import build_rag_index
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope
from sleep_ai_scientist.storage.models import RagChunk


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
        chunk = session.get(RagChunk, "abstract:doi:10.1/a")
        assert chunk is not None
        assert chunk.paper_id == "doi:10.1/a"
        assert chunk.embedding_json is None
    engine.dispose()


def test_rag_index_embeds_chunks_when_enabled(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "lit.db"))

    class FakeEmbeddingClient:
        def __init__(self, model_name, **kwargs):
            self.model_name = model_name

        def embed(self, texts):
            assert texts == ["Insomnia slow wave abstract."]
            return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr("sleep_ai_scientist.literature.rag_indexer.LocalMiniLMEmbeddingClient", FakeEmbeddingClient)
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    with session_scope(engine) as session:
        resolve_and_upsert(
            LiteratureRecord(paper_id="a", title="Sleep abstract", doi="10.1/a", abstract="Insomnia slow wave abstract.", provider="pubmed"),
            session,
            retrieval_channel="api_broad",
        )
        result = build_rag_index(
            session,
            tmp_path / "rag.jsonl",
            embedding_config={
                "provider": "local_minilm",
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "enabled": True,
                "log_file": str(tmp_path / "rag_embedding.log"),
            },
        )
        chunk = session.get(RagChunk, "abstract:doi:10.1/a")
        assert chunk is not None
        assert chunk.embedding_json == [0.1, 0.2, 0.3]
        assert chunk.embedding_dim == 3
        assert chunk.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"

    output = capsys.readouterr().out
    rows = [json.loads(line) for line in (tmp_path / "rag.jsonl").read_text(encoding="utf-8").splitlines()]
    log_rows = [json.loads(line) for line in (tmp_path / "rag_embedding.log").read_text(encoding="utf-8").splitlines()]
    assert result["chunk_count"] == 1
    assert result["embedding"]["enabled"] is True
    assert result["embedding"]["vector_count"] == 1
    assert result["embedding"]["vector_dim"] == 3
    assert rows[0]["embedding"] == [0.1, 0.2, 0.3]
    assert rows[0]["metadata"]["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert "[embedding] rag index start" in output
    assert "[embedding] rag vectors encoded count=1 dim=3" in output
    assert [row["event"] for row in log_rows] == ["rag_index_start", "rag_vectors_encoded", "rag_index_done"]
    engine.dispose()
