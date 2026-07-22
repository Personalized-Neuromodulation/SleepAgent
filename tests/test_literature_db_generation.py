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


def test_literature_build_generates_sqlite_db_with_core_tables(tmp_path, monkeypatch):
    import inspect

    from sleep_ai_scientist.literature import library_builder
    from sleep_ai_scientist.schemas.literature import LiteratureRecord

    assert Path(inspect.getfile(library_builder)).resolve().is_relative_to(Path.cwd().resolve())

    monkeypatch.setattr(
        library_builder,
        "search_literature_apis",
        lambda config, session=None, rate_limit_enabled=True: (
            [
                LiteratureRecord(
                    paper_id="api_online_001",
                    title="Online API sleep RAG paper",
                    abstract="Online insomnia slow wave EEG retrieval produces a RAG-ready abstract.",
                    year=2025,
                    source="api:mock",
                    provider="mock_provider",
                    query="insomnia slow wave EEG",
                )
            ],
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

    assert db_path.exists()
    assert result["registry_records"] == 1
    assert result["rag_index"]["chunk_count"] == 1
    assert (tmp_path / "outputs" / "rag_abstract_chunks.jsonl").exists()

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


def test_online_no_real_data_script_builds_and_validates_literature_db():
    script = Path("scripts/run_foundation_grounding_online.sh").read_text(encoding="utf-8")

    assert "python -m sleep_ai_scientist.cli literature build" in script
    assert "--backend sqlite" in script
    assert "--enable-api" in script
    assert "data/literature/sleep_literature.db" in script
    assert "select count(*) from papers" in script
