from pathlib import Path

import yaml

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline
from sleep_ai_scientist.literature.identity_resolution import resolve_and_upsert
from sleep_ai_scientist.literature.rag_indexer import build_rag_index
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope


def test_grounding_reads_top_k_from_literature_db_rag_without_online_api(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "lit.db"))

    class FakeEmbeddingClient:
        def __init__(self, model_name, **kwargs):
            self.model_name = model_name

        def embed(self, texts):
            vectors = {
                "sleep insomnia thalamocortical slow wave spindle": [1.0, 0.0],
                "Insomnia slow wave associated with ISI and thalamocortical coupling.": [1.0, 0.0],
                "Unrelated paper about appetite.": [0.0, 1.0],
            }
            return [vectors[text] for text in texts]

    monkeypatch.setattr("sleep_ai_scientist.literature.rag_indexer.LocalMiniLMEmbeddingClient", FakeEmbeddingClient)
    monkeypatch.setattr("sleep_ai_scientist.literature.rag_retriever.LocalMiniLMEmbeddingClient", FakeEmbeddingClient)
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    embedding_config = {"provider": "local_minilm", "model": "fake-minilm", "enabled": True, "log_file": str(tmp_path / "embedding.log")}
    with session_scope(engine) as session:
        resolve_and_upsert(
            LiteratureRecord(
                paper_id="api1",
                title="DB slow wave paper",
                abstract="Insomnia slow wave associated with ISI and thalamocortical coupling.",
                doi="10.1/api",
                source="api:pubmed",
                keywords=["slow wave"],
            ),
            session,
            retrieval_channel="api_broad",
        )
        resolve_and_upsert(
            LiteratureRecord(
                paper_id="api2",
                title="Other paper",
                abstract="Unrelated paper about appetite.",
                doi="10.1/other",
                source="api:pubmed",
            ),
            session,
            retrieval_channel="api_broad",
        )
        build_rag_index(session, tmp_path / "rag.jsonl", embedding_config=embedding_config)

    config = load_config("configs/grounding_config.yaml")
    config.pop("_config_path", None)
    config.pop("_project_root", None)
    literature_config = tmp_path / "literature_library_config.yaml"
    literature_config.write_text(yaml.safe_dump({"embedding": embedding_config}, sort_keys=False), encoding="utf-8")
    config["paths"].update(
        {
            "literature_library_config": str(literature_config),
            "output_grounding_dir": str(tmp_path / "grounding"),
            "output_profiles_dir": str(tmp_path / "profiles"),
            "report_path": str(tmp_path / "reports" / "phase1_grounding_report.md"),
            "literature_registry_csv": str(tmp_path / "literature_registry.csv"),
            "literature_registry_jsonl": str(tmp_path / "literature_registry.jsonl"),
            "literature_deduplication_report": str(tmp_path / "literature_deduplication_report.csv"),
            "corpus_manifest": str(tmp_path / "corpus_manifest.json"),
        }
    )
    config.setdefault("api", {})["enabled"] = False
    config["retrieval"]["top_k"] = 1
    config_path = tmp_path / "grounding.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    def fail_search(_config):
        raise AssertionError("grounding should not call online literature APIs when DB RAG is available")

    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fail_search)

    result = run_grounding_pipeline(config_path, corpus_version="db_rag_grounding_v1")

    assert result["papers"] == 1
    assert result["api_papers"] == 0
    assert result["api_summary"]["source"] == "literature_db_rag"
    assert Path(result["literature_registry"]).exists()
    engine.dispose()
