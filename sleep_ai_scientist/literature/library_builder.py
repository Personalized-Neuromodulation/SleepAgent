from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.api.literature_client import apply_query_config, search_literature_apis
from sleep_ai_scientist.common.config import config_path, load_config, resolve_path
from sleep_ai_scientist.common.io import write_csv
from sleep_ai_scientist.grounding.literature_loader import load_literature
from sleep_ai_scientist.literature.anchor_selector import select_anchor_papers, write_anchor_papers
from sleep_ai_scientist.literature.coverage_audit import build_coverage_audit, write_coverage_audit
from sleep_ai_scientist.literature.deduplication import deduplicate_records
from sleep_ai_scientist.literature.manifest import build_library_manifest, write_library_manifest
from sleep_ai_scientist.literature.query_expansion import generate_query_expansion_candidates, write_query_expansion_candidates
from sleep_ai_scientist.literature.query_loader import load_query_set, write_queries_to_db
from sleep_ai_scientist.literature.report import build_library_report, write_library_report
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope
from sleep_ai_scientist.storage.exporters import export_literature_registry_csv_jsonl, export_provider_summary, export_query_summary
from sleep_ai_scientist.storage.repositories import (
    CorpusRepository,
    PaperRepository,
    PaperSourceRepository,
    QueryRepository,
    QueryResultRepository,
    RunRepository,
)


def _path(config: dict[str, Any], key: str) -> Path:
    return config_path(config, key)


def _seed_papers(config: dict[str, Any]) -> list[LiteratureRecord]:
    path = _path(config, "seed_papers")
    if path.exists() and path.stat().st_size > 0:
        return load_literature(path)
    fixture = Path(config["_project_root"]) / "data/fixtures/toy_seed_papers.csv"
    return load_literature(fixture) if fixture.exists() else []


def _write_api_outputs(config: dict[str, Any], api_records: list[LiteratureRecord]) -> None:
    csv_path = _path(config, "api_retrieved_csv")
    jsonl_path = _path(config, "api_retrieved_jsonl")
    rows = [record.model_dump(mode="json") for record in api_records]
    write_csv(csv_path, rows)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _persist_records(session, records: list[LiteratureRecord], queries, query_set_version: str) -> None:  # type: ignore[no-untyped-def]
    paper_repo = PaperRepository()
    source_repo = PaperSourceRepository()
    query_repo = QueryRepository()
    result_repo = QueryResultRepository()
    query_by_text = {query.query_text: query for query in queries}
    for record in records:
        existed = paper_repo.get_by_paper_id(session, record.paper_id) is not None
        paper_repo.upsert_paper(session, record)
        source_repo.add_source(
            session,
            record.paper_id,
            provider=record.provider or record.source or "seed",
            provider_id=record.provider_id,
            query_text=getattr(record, "query", None),
            query_group=_query_group_for_record(record, query_by_text),
            query_set_version=query_set_version,
            raw_json=record.model_dump(mode="json"),
        )
        query_text = getattr(record, "query", None)
        if query_text and query_text in query_by_text:
            query = query_by_text[query_text]
            query_repo.upsert_query(session, query.query_text, query.query_group, query.query_set_version, query.priority)
            result_repo.add_result(session, query.query_id, record.provider or record.source or "api", record.paper_id, is_new_record=not existed)


def _query_group_for_record(record: LiteratureRecord, query_by_text: dict[str, Any]) -> str | None:
    query_text = getattr(record, "query", None)
    if query_text and query_text in query_by_text:
        return query_by_text[query_text].query_group
    return None


def run_literature_build(
    config_path_value: str | Path = "configs/literature_library_config.yaml",
    *,
    query_config_path: str | Path = "configs/sleep_literature_queries.yaml",
    library_version: str | None = None,
    backend: str | None = None,
    session=None,
    api_session=None,
    rate_limit_enabled: bool = True,
    api_enabled: bool | None = None,
) -> dict[str, Any]:
    config = load_config(config_path_value)
    if api_enabled is not None:
        config.setdefault("api", {})["enabled"] = api_enabled
    root = Path(config["_project_root"])
    query_config = resolve_path(query_config_path, root)
    query_payload, queries = load_query_set(query_config)
    query_set_version = query_payload.get("query_set", {}).get("version", "")
    library_version = library_version or config.get("project", {}).get("library_version", "sleep_literature_library_v1")

    db_config_path = resolve_path(config.get("database_config", "configs/database_config.yaml"), root)
    engine = create_engine_from_config(db_config_path, backend=backend)
    init_database(engine)

    def _run(session_obj) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        run_repo = RunRepository()
        run = run_repo.create_run(session_obj, "literature_build", str(config_path_value), str(query_config_path), library_version)
        warnings: list[str] = []
        seed_papers = _seed_papers(config)
        api_config = apply_query_config(config, query_config)
        api_papers: list[LiteratureRecord] = []
        api_summary: dict[str, Any] = {"enabled": False, "warnings": []}
        if api_config.get("api", {}).get("enabled", False):
            try:
                api_papers, api_summary = search_literature_apis(api_config, session=api_session, rate_limit_enabled=rate_limit_enabled)
            except Exception as exc:
                warnings.append(str(exc))
                if not api_config.get("api", {}).get("fail_open", True):
                    raise
        _write_api_outputs(config, api_papers)
        seed_ids = {paper.paper_id for paper in seed_papers}
        registry, duplicate_report = deduplicate_records(seed_papers + api_papers, seed_ids)
        write_csv(_path(config, "deduplication_report"), duplicate_report)
        write_queries_to_db(session_obj, queries)
        _persist_records(session_obj, registry, queries, query_set_version)
        export_literature_registry_csv_jsonl(session_obj, _path(config, "registry_csv"), _path(config, "registry_jsonl"))
        query_summary = export_query_summary(session_obj, _path(config, "query_summary"))
        provider_summary = export_provider_summary(session_obj, _path(config, "provider_summary"))
        query_groups = list(query_payload.get("queries", {}).keys())
        coverage = build_coverage_audit(registry, query_groups, len(duplicate_report))
        coverage_csv = config_path(config, "query_coverage_audit", "outputs/literature/query_coverage_audit.csv")
        coverage_json = config_path(config, "coverage_audit", "outputs/literature/coverage_audit.json")
        write_coverage_audit(coverage, coverage_csv, coverage_json)
        anchors = select_anchor_papers(registry, query_groups)
        anchor_path = config_path(config, "anchor_papers", "outputs/literature/anchor_papers.csv")
        write_anchor_papers(anchor_path, anchors)
        expansion = generate_query_expansion_candidates(registry, [query.query_text for query in queries])
        expansion_path = config_path(config, "query_expansion_candidates", "outputs/literature/query_expansion_candidates.csv")
        write_query_expansion_candidates(expansion_path, expansion)
        corpus_repo = CorpusRepository()
        corpus_repo.create_or_update_corpus_version(
            session_obj,
            library_version,
            library_version=library_version,
            query_set_version=query_set_version,
            manifest_path=str(_path(config, "manifest")),
            registry_csv_path=str(_path(config, "registry_csv")),
            registry_jsonl_path=str(_path(config, "registry_jsonl")),
            report_path=str(_path(config, "build_report")),
            notes="Sleep literature library build",
        )
        paths = {**config.get("paths", {}), "coverage_audit": str(coverage_json), "anchor_papers": str(anchor_path), "query_expansion_candidates": str(expansion_path)}
        manifest = build_library_manifest(
            library_version,
            query_set_version,
            paths,
            {"seed_papers": len(seed_papers), "api_papers": len(api_papers), "registry_records": len(registry), "duplicate_groups": len(duplicate_report)},
            "Sleep Literature Library v1",
        )
        write_library_manifest(_path(config, "manifest"), manifest)
        summary = {
            "library_version": library_version,
            "query_set_version": query_set_version,
            "seed_papers": len(seed_papers),
            "api_papers": len(api_papers),
            "registry_records": len(registry),
            "duplicate_groups": len(duplicate_report),
            "provider_summary": provider_summary,
            "query_summary": query_summary,
            "coverage_audit": str(coverage_json),
            "anchor_papers": str(anchor_path),
            "query_expansion_candidates": str(expansion_path),
            "manifest": str(_path(config, "manifest")),
            "warnings": warnings + api_summary.get("warnings", []),
        }
        write_library_report(_path(config, "build_report"), build_library_report(summary))
        run_repo.finish_run(session_obj, run.run_id, "completed")
        summary["run_id"] = run.run_id
        return summary

    if session is not None:
        return _run(session)
    with session_scope(engine) as session_obj:
        result = _run(session_obj)
    engine.dispose()
    return result
