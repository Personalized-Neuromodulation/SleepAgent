from pathlib import Path

import yaml

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline
from tests.api_test_utils import fake_online_literature_search


def _tmp_config(tmp_path: Path) -> Path:
    config = load_config("configs/grounding_config.yaml")
    config.pop("_config_path", None)
    config.pop("_project_root", None)
    database_config = tmp_path / "database_config.yaml"
    database_config.write_text(
        yaml.safe_dump(
            {
                "database": {
                    "enabled": True,
                    "backend_env": "SLEEPAGENT_DATABASE_BACKEND",
                    "default_backend": "sqlite",
                    "sqlite_path_env": "SLEEPAGENT_SQLITE_PATH",
                    "default_sqlite_path": str(tmp_path / "literature.db"),
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    literature_config = tmp_path / "literature_library_config.yaml"
    literature_config.write_text(yaml.safe_dump({"embedding": {"enabled": False}}, sort_keys=False), encoding="utf-8")
    config.setdefault("api", {})["enabled"] = True
    config["paths"].update(
        {
            "database_config": str(database_config),
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
    path = tmp_path / "grounding.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_grounding_pipeline_generates_outputs(monkeypatch, tmp_path):
    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fake_online_literature_search)
    result = run_grounding_pipeline(_tmp_config(tmp_path))
    assert result["evidence"] > 0
    required = [
        tmp_path / "grounding" / "evidence_table.csv",
        tmp_path / "grounding" / "evidence_table.json",
        tmp_path / "grounding" / "mechanism_graph_nodes.csv",
        tmp_path / "grounding" / "mechanism_graph_edges.csv",
        tmp_path / "grounding" / "mechanism_graph.json",
        tmp_path / "grounding" / "llm_evidence_context.json",
        tmp_path / "grounding" / "llm_mechanism_context.json",
        tmp_path / "grounding" / "llm_context_compression_manifest.json",
        tmp_path / "grounding" / "evidence_to_variable_map.yaml",
        tmp_path / "grounding" / "approved_variables_from_grounding.yaml",
        tmp_path / "profiles" / "theoretical_profile.yaml",
        tmp_path / "profiles" / "observed_profile.yaml",
        tmp_path / "profiles" / "analysis_ready_profile.yaml",
        tmp_path / "reports" / "phase1_grounding_report.md",
    ]
    for path in required:
        assert Path(path).exists()
    assert Path(result["llm_context_compression"]["llm_evidence_context_json"]).exists()
    assert Path(result["llm_context_compression"]["llm_mechanism_context_json"]).exists()


def test_grounding_pipeline_reads_embedding_config_from_literature_config_for_db_rag(monkeypatch, tmp_path):
    config_path = _tmp_config(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    literature_config = tmp_path / "literature_library_config.yaml"
    literature_embedding = {
        "provider": "local_minilm",
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "enabled": True,
        "log_file": str(tmp_path / "embedding.log"),
    }
    literature_config.write_text(yaml.safe_dump({"embedding": literature_embedding}, sort_keys=False), encoding="utf-8")
    config["paths"]["literature_library_config"] = str(literature_config)
    config.pop("embedding", None)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    seen = {}

    def fake_db_rag_retrieve(session, query, *, top_k=10, embedding_config=None):
        seen["query"] = query
        seen["top_k"] = top_k
        seen["embedding_config"] = embedding_config
        return [], {"source": "literature_db_rag", "enabled": True, "retrieval_hits": 0, "available_chunks": 0}

    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fake_online_literature_search)
    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.retrieve_literature_records_from_db", fake_db_rag_retrieve)

    run_grounding_pipeline(config_path)

    assert seen["embedding_config"] == literature_embedding


def test_grounding_pipeline_accepts_dynamic_retrieval_query(monkeypatch, tmp_path):
    config_path = _tmp_config(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    literature_config = tmp_path / "literature_library_config.yaml"
    literature_embedding = {"provider": "local_minilm", "model": "sentence-transformers/all-MiniLM-L6-v2", "enabled": True}
    literature_config.write_text(yaml.safe_dump({"embedding": literature_embedding}, sort_keys=False), encoding="utf-8")
    config["paths"]["literature_library_config"] = str(literature_config)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    seen = {}

    def fake_db_rag_retrieve(session, query, *, top_k=10, embedding_config=None):
        seen["query"] = query
        seen["top_k"] = top_k
        return [], {"source": "literature_db_rag", "enabled": True, "retrieval_hits": 0, "available_chunks": 0}

    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fake_online_literature_search)
    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.retrieve_literature_records_from_db", fake_db_rag_retrieve)

    run_grounding_pipeline(config_path, retrieval_query="thalamus default mode network sleep fMRI")

    assert seen["query"] == "thalamus default mode network sleep fMRI"


def test_grounding_pipeline_skips_llm_context_when_disabled(monkeypatch, tmp_path):
    config_path = _tmp_config(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["llm_context_compression"]["enabled"] = False
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fake_online_literature_search)
    result = run_grounding_pipeline(config_path)

    assert result["llm_context_compression"] == {"enabled": False}
    assert not (tmp_path / "grounding" / "llm_evidence_context.json").exists()
    assert not (tmp_path / "grounding" / "llm_mechanism_context.json").exists()
