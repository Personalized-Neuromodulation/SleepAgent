from sleep_ai_scientist.literature.identity_resolution import resolve_and_upsert
from sleep_ai_scientist.literature.rag_indexer import build_rag_index
from sleep_ai_scientist.literature.rag_retriever import retrieve_literature_records_from_db
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope


def test_retrieve_literature_records_from_db_uses_saved_embeddings(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "lit.db"))

    class FakeEmbeddingClient:
        def __init__(self, model_name, **kwargs):
            self.model_name = model_name

        def embed(self, texts):
            vectors = {
                "query insomnia slow wave": [1.0, 0.0],
                "Insomnia slow-wave thalamocortical abstract.": [1.0, 0.0],
                "Unrelated appetite study.": [0.0, 1.0],
            }
            return [vectors[text] for text in texts]

    monkeypatch.setattr("sleep_ai_scientist.literature.rag_indexer.LocalMiniLMEmbeddingClient", FakeEmbeddingClient)
    monkeypatch.setattr("sleep_ai_scientist.literature.rag_retriever.LocalMiniLMEmbeddingClient", FakeEmbeddingClient)
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    embedding_config = {
        "provider": "local_minilm",
        "model": "fake-minilm",
        "enabled": True,
        "log_file": str(tmp_path / "embedding.log"),
    }
    with session_scope(engine) as session:
        resolve_and_upsert(
            LiteratureRecord(
                paper_id="sleep",
                title="Insomnia paper",
                doi="10.1/sleep",
                abstract="Insomnia slow-wave thalamocortical abstract.",
                provider="pubmed",
            ),
            session,
            retrieval_channel="api_broad",
        )
        resolve_and_upsert(
            LiteratureRecord(
                paper_id="other",
                title="Other paper",
                doi="10.1/other",
                abstract="Unrelated appetite study.",
                provider="pubmed",
            ),
            session,
            retrieval_channel="api_broad",
        )
        build_rag_index(session, tmp_path / "rag.jsonl", embedding_config=embedding_config)
        records, summary = retrieve_literature_records_from_db(session, "query insomnia slow wave", top_k=1, embedding_config=embedding_config)

    assert [record.paper_id for record in records] == ["doi:10.1/sleep"]
    assert summary["source"] == "literature_db_rag"
    assert summary["retrieval_hits"] == 1
    assert summary["available_chunks"] == 2
    engine.dispose()


def test_retrieve_literature_records_from_db_uses_keyword_fallback_when_embedding_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "lit.db"))
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    with session_scope(engine) as session:
        resolve_and_upsert(
            LiteratureRecord(
                paper_id="sleep",
                title="Insomnia thalamocortical paper",
                doi="10.1/sleep",
                abstract="Insomnia slow wave thalamocortical coupling abstract.",
                provider="pubmed",
            ),
            session,
            retrieval_channel="api_broad",
        )
        resolve_and_upsert(
            LiteratureRecord(
                paper_id="other",
                title="Other paper",
                doi="10.1/other",
                abstract="Unrelated appetite study.",
                provider="pubmed",
            ),
            session,
            retrieval_channel="api_broad",
        )
        build_rag_index(session, tmp_path / "rag.jsonl", embedding_config={"enabled": False})
        records, summary = retrieve_literature_records_from_db(
            session,
            "insomnia slow wave thalamocortical",
            top_k=1,
            embedding_config={"enabled": False, "log_file": str(tmp_path / "retrieval.log")},
        )

    assert [record.paper_id for record in records] == ["doi:10.1/sleep"]
    assert summary["source"] == "literature_db_rag"
    assert summary["retrieval_mode"] == "keyword"
    assert summary["retrieval_hits"] == 1
    assert summary["available_chunks"] == 2
    engine.dispose()
