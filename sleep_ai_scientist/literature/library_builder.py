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
from sleep_ai_scientist.literature.identity_resolution import export_deduplication_artifacts, resolve_and_upsert
from sleep_ai_scientist.literature.journal_targeted_retriever import retrieve_journal_targeted_records, write_journal_targeted_outputs
from sleep_ai_scientist.literature.manifest import build_library_manifest, write_library_manifest
from sleep_ai_scientist.literature.query_expansion import generate_query_expansion_candidates, write_query_expansion_candidates
from sleep_ai_scientist.literature.query_loader import load_query_set, write_queries_to_db
from sleep_ai_scientist.literature.rag_indexer import build_rag_index
from sleep_ai_scientist.literature.report import build_library_report, write_library_report
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope
from sleep_ai_scientist.storage.exporters import export_literature_registry_csv_jsonl, export_provider_summary, export_query_summary
from sleep_ai_scientist.storage.models import Paper
from sleep_ai_scientist.storage.repositories import (
    CorpusRepository,
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


def _persist_records(session, records: list[LiteratureRecord], queries, query_set_version: str, retrieval_channel: str = "unknown") -> list[Any]:  # type: ignore[no-untyped-def]
    query_by_text = {query.query_text: query for query in queries}
    results = []
    for record in records:
        if getattr(record, "query", None) and not getattr(record, "query_group", None):
            record.query_group = _query_group_for_record(record, query_by_text)
        result = resolve_and_upsert(
            record,
            session,
            retrieval_channel=getattr(record, "retrieval_channel", None) or retrieval_channel,
            query_lookup=query_by_text,
            query_set_version=query_set_version,
        )
        results.append(result)
    return results


def _query_group_for_record(record: LiteratureRecord, query_by_text: dict[str, Any]) -> str | None:
    query_text = getattr(record, "query", None)
    if query_text and query_text in query_by_text:
        return query_by_text[query_text].query_group
    return None


def _paper_to_record(paper: Paper) -> LiteratureRecord:
    return LiteratureRecord(
        paper_id=paper.paper_id,
        title=paper.title,
        abstract=paper.abstract or "",
        year=paper.year,
        doi=paper.doi or "",
        pmid=paper.pmid or "",
        pmcid=paper.pmcid,
        source=";".join(paper.source_providers_json or []) or (paper.source or ""),
        keywords=paper.keywords_json or [],
        url=paper.url or "",
        journal=paper.journal,
        publication_type=paper.publication_type,
        authors=paper.authors_json or [],
        citation_count=paper.citation_count,
        citation_source=paper.citation_source,
        citation_count_age_normalized=paper.citation_count_age_normalized,
        is_open_access=paper.is_open_access,
        provider=";".join(paper.source_providers_json or []),
        semantic_scholar_id=paper.semantic_scholar_id,
        openalex_id=paper.openalex_id,
        crossref_id=paper.crossref_id,
        first_author=paper.first_author,
        retrieval_channel=";".join(paper.retrieval_channels_json or []),
        journal_priority_score=paper.journal_priority_score,
    )


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
    enable_journal_targeted: bool = False,
    enable_rag_index: bool = False,
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
        journal_targeted_records: list[LiteratureRecord] = []
        if enable_journal_targeted or config.get("journal_targeted", {}).get("enabled", False):
            journal_targeted_records = retrieve_journal_targeted_records(config)
            write_journal_targeted_outputs(config, journal_targeted_records)
        write_queries_to_db(session_obj, queries)
        seed_results = _persist_records(session_obj, seed_papers, queries, query_set_version, "manual_seed")
        api_results = _persist_records(session_obj, api_papers, queries, query_set_version, "api_broad")
        targeted_results = _persist_records(session_obj, journal_targeted_records, queries, query_set_version, "journal_targeted")
        dedup_paths = export_deduplication_artifacts(
            session_obj,
            _path(config, "deduplication_report"),
            config_path(config, "deduplication_summary", "outputs/literature/deduplication_summary.json"),
            config_path(config, "deduplication_manual_review", "outputs/literature/deduplication_manual_review.csv"),
        )
        export_literature_registry_csv_jsonl(session_obj, _path(config, "registry_csv"), _path(config, "registry_jsonl"))
        registry = session_obj.query(Paper).all()
        query_summary = export_query_summary(session_obj, _path(config, "query_summary"))
        provider_summary = export_provider_summary(session_obj, _path(config, "provider_summary"))
        query_groups = list(query_payload.get("queries", {}).keys())
        coverage = build_coverage_audit([_paper_to_record(paper) for paper in registry], query_groups, dedup_paths["summary"]["merged_duplicate_count"])
        coverage_csv = config_path(config, "query_coverage_audit", "outputs/literature/query_coverage_audit.csv")
        coverage_json = config_path(config, "coverage_audit", "outputs/literature/coverage_audit.json")
        write_coverage_audit(coverage, coverage_csv, coverage_json)
        registry_records = [_paper_to_record(paper) for paper in registry]
        anchors = select_anchor_papers(registry_records, query_groups)
        anchor_path = config_path(config, "anchor_papers", "outputs/literature/anchor_papers.csv")
        write_anchor_papers(anchor_path, anchors)
        expansion = generate_query_expansion_candidates(registry_records, [query.query_text for query in queries])
        expansion_path = config_path(config, "query_expansion_candidates", "outputs/literature/query_expansion_candidates.csv")
        write_query_expansion_candidates(expansion_path, expansion)
        rag_result = None
        if enable_rag_index or config.get("rag_index", {}).get("enabled", False):
            rag_result = build_rag_index(session_obj, config_path(config, "rag_index_jsonl", "outputs/literature/rag_abstract_chunks.jsonl"))
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
            {
                "seed_papers": len(seed_papers),
                "api_papers": len(api_papers),
                "journal_targeted_records": len(journal_targeted_records),
                "registry_records": len(registry),
                "duplicate_groups": dedup_paths["summary"]["merged_duplicate_count"],
            },
            "Sleep Literature Library v1",
        )
        write_library_manifest(_path(config, "manifest"), manifest)
        summary = {
            "library_version": library_version,
            "query_set_version": query_set_version,
            "seed_papers": len(seed_papers),
            "api_papers": len(api_papers),
            "journal_targeted_records": len(journal_targeted_records),
            "registry_records": len(registry),
            "duplicate_groups": dedup_paths["summary"]["merged_duplicate_count"],
            "deduplication": dedup_paths,
            "rag_index": rag_result,
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
