from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _query_config(tmp_path: Path) -> Path:
    return _write_yaml(
        tmp_path / "queries.yaml",
        {
            "query_set": {"version": "test_sleep_queries_v1"},
            "queries": {"core": ["insomnia slow wave EEG"]},
            "settings": {"max_results_per_query": 1, "providers": []},
        },
    )


def _library_config(tmp_path: Path) -> Path:
    return _write_yaml(
        tmp_path / "literature_library_config.yaml",
        {
            "project": {"name": "SleepAgent", "module": "sleep_literature_library"},
            "database_config": str(tmp_path / "database_config.yaml"),
            "paths": {
                "api_retrieved_csv": str(tmp_path / "literature" / "sleep_library_api_retrieved_papers.csv"),
                "api_retrieved_jsonl": str(tmp_path / "literature" / "sleep_library_api_retrieved_papers.jsonl"),
                "registry_csv": str(tmp_path / "literature" / "sleep_literature_registry.csv"),
                "registry_jsonl": str(tmp_path / "literature" / "sleep_literature_registry.jsonl"),
                "deduplication_report": str(tmp_path / "literature" / "literature_deduplication_report.csv"),
                "deduplication_summary": str(tmp_path / "literature" / "deduplication_summary.json"),
                "deduplication_manual_review": str(tmp_path / "literature" / "deduplication_manual_review.csv"),
                "manifest": str(tmp_path / "outputs" / "sleep_library_manifest.json"),
                "build_report": str(tmp_path / "outputs" / "sleep_library_build_report.md"),
                "provider_summary": str(tmp_path / "outputs" / "provider_summary.json"),
                "query_summary": str(tmp_path / "outputs" / "query_summary.csv"),
                "query_coverage_audit": str(tmp_path / "outputs" / "query_coverage_audit.csv"),
                "coverage_audit": str(tmp_path / "outputs" / "coverage_audit.json"),
                "anchor_papers": str(tmp_path / "outputs" / "anchor_papers.csv"),
                "query_expansion_candidates": str(tmp_path / "outputs" / "query_expansion_candidates.csv"),
                "rag_index_jsonl": str(tmp_path / "outputs" / "rag_abstract_chunks.jsonl"),
            },
            "api": {"enabled": False},
            "embedding": {"enabled": False},
        },
    )


def _database_config(tmp_path: Path) -> Path:
    return _write_yaml(
        tmp_path / "database_config.yaml",
        {
            "database": {
                "enabled": True,
                "backend_env": "SLEEPAGENT_DATABASE_BACKEND",
                "default_backend": "sqlite",
                "sqlite_path_env": "SLEEPAGENT_SQLITE_PATH",
                "default_sqlite_path": str(tmp_path / "literature" / "sleep_literature.db"),
            }
        },
    )


def test_literature_build_generates_sqlite_db_with_core_tables(tmp_path, monkeypatch, capsys):
    import inspect

    from sleep_ai_scientist.literature import library_builder
    from sleep_ai_scientist.api.normalizer import api_to_literature_record, make_api_record

    assert Path(inspect.getfile(library_builder)).resolve().is_relative_to(Path.cwd().resolve())

    api_record = make_api_record(
        "mock_provider",
        "api_online_001",
        "Online API sleep RAG paper",
        abstract="Online insomnia slow wave EEG retrieval produces a RAG-ready abstract.",
        year=2025,
        source="api:mock",
        query="insomnia slow wave EEG",
    )
    monkeypatch.setattr(
        library_builder,
        "search_literature_apis",
        lambda config, session=None, rate_limit_enabled=True: (
            [api_to_literature_record(api_record)],
            {"enabled": True, "warnings": []},
        ),
    )

    db_path = tmp_path / "literature" / "sleep_literature.db"
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(db_path))
    _database_config(tmp_path)

    result = library_builder.run_literature_build(
        _library_config(tmp_path),
        query_config_path=_query_config(tmp_path),
        library_version="test_sleep_library_v1",
        backend="sqlite",
        api_enabled=True,
        enable_rag_index=True,
    )
    output = capsys.readouterr().out

    assert db_path.exists()
    assert result["registry_records"] == 1
    assert result["rag_index"]["chunk_count"] == 1
    assert (tmp_path / "outputs" / "rag_abstract_chunks.jsonl").exists()
    assert "[literature_build] persist_api_records_start count=1" in output
    assert "[literature_build] persist_api_records_done count=1" in output
    assert "[literature_build] export_registry_start" in output
    assert "[literature_build] report_done" in output

    with sqlite3.connect(db_path) as conn:
        counts = {
            table: conn.execute(f"select count(*) from {table}").fetchone()[0]
            for table in ["papers", "queries", "query_results", "corpus_versions", "build_runs"]
        }

    assert counts == {
        "papers": 1,
        "queries": 1,
        "query_results": 1,
        "corpus_versions": 1,
        "build_runs": 1,
    }


def test_online_foundation_script_builds_and_validates_literature_db():
    script = Path("scripts/run_foundation_grounding_online.sh").read_text(encoding="utf-8")

    assert "python -m sleep_ai_scientist.cli literature build" in script
    assert "--backend sqlite" in script
    assert "--enable-api" in script
    assert "data/literature/sleep_literature.db" in script
    assert "select count(*) from papers" in script
    assert script.index("[3/6] Build online sleep literature SQLite DB") < script.index("[4/6] Run grounding from unified literature DB RAG")
    assert "--enable-rag-index" in script
    assert "select count(*) from rag_chunks" in script


def test_literature_build_uses_own_embedding_config_for_rag_index(tmp_path, monkeypatch):
    from sleep_ai_scientist.literature import library_builder
    from sleep_ai_scientist.api.normalizer import api_to_literature_record, make_api_record

    api_record = make_api_record(
        "mock_provider",
        "api_online_001",
        "Online API sleep RAG paper",
        abstract="Online insomnia slow wave EEG retrieval produces a RAG-ready abstract.",
        year=2025,
        source="api:mock",
        query="insomnia slow wave EEG",
    )
    monkeypatch.setattr(
        library_builder,
        "search_literature_apis",
        lambda config, session=None, rate_limit_enabled=True: (
            [api_to_literature_record(api_record)],
            {"enabled": True, "warnings": []},
        ),
    )
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "literature" / "sleep_literature.db"))
    _database_config(tmp_path)
    library_config = yaml.safe_load(_library_config(tmp_path).read_text(encoding="utf-8"))
    library_config["embedding"] = {
        "provider": "local_minilm",
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "enabled": True,
        "log_file": str(tmp_path / "embedding.log"),
    }
    config_path = _write_yaml(tmp_path / "literature_library_config_embedding.yaml", library_config)

    def fake_build_rag_index(session, output_jsonl, embedding_config=None, *, write_jsonl=True):
        Path(output_jsonl).parent.mkdir(parents=True, exist_ok=True)
        if write_jsonl:
            Path(output_jsonl).write_text("", encoding="utf-8")
        return {
            "chunk_count": 1,
            "path": str(output_jsonl) if write_jsonl else None,
            "embedding": {
                "enabled": bool(embedding_config.get("enabled")),
                "model": embedding_config.get("model"),
                "vector_count": 1,
                "vector_dim": 384,
            },
        }

    monkeypatch.setattr(library_builder, "build_rag_index", fake_build_rag_index)

    result = library_builder.run_literature_build(
        config_path,
        query_config_path=_query_config(tmp_path),
        library_version="test_sleep_library_v1",
        backend="sqlite",
        api_enabled=True,
    )

    assert result["rag_index"]["embedding"]["enabled"] is True
    assert result["rag_index"]["embedding"]["model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert result["rag_index"]["embedding"]["vector_dim"] == 384


def test_literature_build_can_skip_duplicate_jsonl_exports(tmp_path, monkeypatch):
    from sleep_ai_scientist.literature import library_builder
    from sleep_ai_scientist.api.normalizer import api_to_literature_record, make_api_record

    api_record = make_api_record(
        "mock_provider",
        "api_online_001",
        "Online API sleep RAG paper",
        abstract="Online insomnia slow wave EEG retrieval produces a RAG-ready abstract.",
        year=2025,
        source="api:mock",
        query="insomnia slow wave EEG",
    )
    monkeypatch.setattr(
        library_builder,
        "search_literature_apis",
        lambda config, session=None, rate_limit_enabled=True: (
            [api_to_literature_record(api_record)],
            {"enabled": True, "warnings": []},
        ),
    )

    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "literature" / "sleep_literature.db"))
    _database_config(tmp_path)
    library_config = yaml.safe_load(_library_config(tmp_path).read_text(encoding="utf-8"))
    library_config["outputs"] = {"write_jsonl": False, "write_rag_jsonl": False}
    config_path = _write_yaml(tmp_path / "literature_library_config_no_jsonl.yaml", library_config)

    result = library_builder.run_literature_build(
        config_path,
        query_config_path=_query_config(tmp_path),
        library_version="test_sleep_library_v1",
        backend="sqlite",
        api_enabled=True,
        enable_rag_index=True,
    )

    assert result["rag_index"]["chunk_count"] == 1
    assert result["rag_index"]["path"] is None
    assert not (tmp_path / "literature" / "sleep_library_api_retrieved_papers.jsonl").exists()
    assert not (tmp_path / "outputs" / "rag_abstract_chunks.jsonl").exists()
