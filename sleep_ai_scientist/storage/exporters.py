from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sleep_ai_scientist.common.io import ensure_parent, write_csv, write_json, write_yaml
from sleep_ai_scientist.storage.models import (
    ClinicalTrial,
    CorpusVersion,
    DiagnosticTerm,
    Guideline,
    Instrument,
    Paper,
    PaperSource,
    PublicDataset,
    Query,
    QueryResult,
    StandardRule,
    ToolMethod,
)


def _json_string(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _paper_row(paper: Paper) -> dict[str, Any]:
    return {
        "paper_id": paper.paper_id,
        "title": paper.title,
        "abstract": paper.abstract or "",
        "year": paper.year or "",
        "doi": paper.doi or "",
        "pmid": paper.pmid or "",
        "pmcid": paper.pmcid or "",
        "journal": paper.journal or "",
        "publication_type": paper.publication_type or "",
        "authors": _json_string(paper.authors_json or []),
        "keywords": _json_string(paper.keywords_json or []),
        "mesh_terms": _json_string(paper.mesh_terms_json or []),
        "citation_count": paper.citation_count if paper.citation_count is not None else "",
        "citation_source": paper.citation_source or "",
        "citation_count_age_normalized": paper.citation_count_age_normalized if paper.citation_count_age_normalized is not None else "",
        "is_open_access": paper.is_open_access if paper.is_open_access is not None else "",
        "open_access_url": paper.open_access_url or "",
        "url": paper.url or "",
        "source": paper.source or "",
        "created_at": paper.created_at.isoformat() if paper.created_at else "",
        "updated_at": paper.updated_at.isoformat() if paper.updated_at else "",
    }


def export_literature_registry_csv_jsonl(session: Session, output_csv: str | Path, output_jsonl: str | Path) -> dict[str, Any]:
    papers = list(session.scalars(select(Paper).order_by(Paper.paper_id)))
    rows = [_paper_row(paper) for paper in papers]
    write_csv(Path(output_csv), rows)
    ensure_parent(Path(output_jsonl))
    with Path(output_jsonl).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"paper_count": len(rows), "csv": str(output_csv), "jsonl": str(output_jsonl)}


def export_query_summary(session: Session, output_csv: str | Path) -> dict[str, Any]:
    rows = []
    for query in session.scalars(select(Query).order_by(Query.query_group, Query.query_text)):
        count = session.scalar(select(func.count()).select_from(QueryResult).where(QueryResult.query_id == query.query_id)) or 0
        rows.append(
            {
                "query_id": query.query_id,
                "query_text": query.query_text,
                "query_group": query.query_group,
                "query_set_version": query.query_set_version,
                "priority": query.priority,
                "status": query.status,
                "result_count": int(count),
            }
        )
    write_csv(Path(output_csv), rows)
    return {"query_count": len(rows), "path": str(output_csv)}


def export_provider_summary(session: Session, output_json: str | Path) -> dict[str, Any]:
    result_counts = {
        str(provider): int(count)
        for provider, count in session.execute(select(QueryResult.provider, func.count()).group_by(QueryResult.provider)).all()
    }
    source_counts = {
        str(provider): int(count)
        for provider, count in session.execute(select(PaperSource.provider, func.count()).group_by(PaperSource.provider)).all()
        if provider
    }
    payload = {"query_result_counts": result_counts, "paper_source_counts": source_counts}
    write_json(Path(output_json), payload)
    return payload


def export_corpus_manifest(session: Session, corpus_version: str, output_path: str | Path) -> dict[str, Any]:
    corpus = session.get(CorpusVersion, corpus_version)
    paper_count = int(session.scalar(select(func.count()).select_from(Paper)) or 0)
    query_count = int(session.scalar(select(func.count()).select_from(Query)) or 0)
    payload = {
        "corpus_version": corpus_version,
        "library_version": corpus.library_version if corpus else "",
        "query_set_version": corpus.query_set_version if corpus else "",
        "created_at": corpus.created_at.isoformat() if corpus and corpus.created_at else "",
        "frozen": bool(corpus.frozen) if corpus else False,
        "paper_count": paper_count,
        "query_count": query_count,
        "registry_csv_path": corpus.registry_csv_path if corpus else "",
        "registry_jsonl_path": corpus.registry_jsonl_path if corpus else "",
        "report_path": corpus.report_path if corpus else "",
        "notes": corpus.notes if corpus else "",
    }
    write_json(Path(output_path), payload)
    return payload


def export_phase1_literature_artifacts(session: Session, corpus_version: str, output_config: dict[str, Any]) -> dict[str, Any]:
    registry = export_literature_registry_csv_jsonl(session, output_config["registry_csv"], output_config["registry_jsonl"])
    query_summary = export_query_summary(session, output_config["query_summary"])
    provider_summary = export_provider_summary(session, output_config["provider_summary"])
    manifest = export_corpus_manifest(session, corpus_version, output_config["manifest"])
    return {
        "registry": registry,
        "query_summary": query_summary,
        "provider_summary": provider_summary,
        "manifest": manifest,
    }


def _model_rows(session: Session, model, order_column: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    rows = []
    for item in session.scalars(select(model).order_by(getattr(model, order_column))):
        payload = {column.name: getattr(item, column.name) for column in item.__table__.columns}
        for key, value in list(payload.items()):
            if key.endswith("_json"):
                payload[key] = value or [] if not isinstance(value, str) else value
            elif hasattr(value, "isoformat"):
                payload[key] = value.isoformat()
        rows.append(payload)
    return rows


def _csv_safe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe = []
    for row in rows:
        safe.append({key: _json_string(value) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    return safe


def _write_csv_jsonl(rows: list[dict[str, Any]], output_csv: str | Path, output_jsonl: str | Path) -> dict[str, Any]:
    write_csv(Path(output_csv), _csv_safe(rows))
    ensure_parent(Path(output_jsonl))
    with Path(output_jsonl).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"count": len(rows), "csv": str(output_csv), "jsonl": str(output_jsonl)}


def export_clinical_trials_csv_jsonl(session: Session, output_csv: str | Path, output_jsonl: str | Path) -> dict[str, Any]:
    return _write_csv_jsonl(_model_rows(session, ClinicalTrial, "nct_id"), output_csv, output_jsonl)


def export_guidelines_csv_jsonl(session: Session, output_csv: str | Path, output_jsonl: str | Path) -> dict[str, Any]:
    return _write_csv_jsonl(_model_rows(session, Guideline, "title"), output_csv, output_jsonl)


def export_standards_csv_jsonl(session: Session, output_csv: str | Path, output_jsonl: str | Path) -> dict[str, Any]:
    return _write_csv_jsonl(_model_rows(session, StandardRule, "standard_id"), output_csv, output_jsonl)


def export_datasets_csv_jsonl(session: Session, output_csv: str | Path, output_jsonl: str | Path) -> dict[str, Any]:
    return _write_csv_jsonl(_model_rows(session, PublicDataset, "dataset_id"), output_csv, output_jsonl)


def _write_yaml_json(payload: dict[str, Any], output_yaml: str | Path, output_json: str | Path) -> dict[str, Any]:
    write_yaml(Path(output_yaml), payload)
    write_json(Path(output_json), payload)
    return {"yaml": str(output_yaml), "json": str(output_json)}


def export_diagnostic_taxonomy_yaml_json(session: Session, output_yaml: str | Path, output_json: str | Path) -> dict[str, Any]:
    rows = _model_rows(session, DiagnosticTerm, "term_id")
    payload = {"diagnostic_terms": rows}
    return {"count": len(rows), **_write_yaml_json(payload, output_yaml, output_json)}


def export_instruments_yaml_json(session: Session, output_yaml: str | Path, output_json: str | Path) -> dict[str, Any]:
    rows = _model_rows(session, Instrument, "instrument_id")
    payload = {"instruments": rows}
    return {"count": len(rows), **_write_yaml_json(payload, output_yaml, output_json)}


def export_tools_methods_yaml_json(session: Session, output_yaml: str | Path, output_json: str | Path) -> dict[str, Any]:
    rows = _model_rows(session, ToolMethod, "tool_id")
    payload = {"tools_methods": rows}
    return {"count": len(rows), **_write_yaml_json(payload, output_yaml, output_json)}


def export_knowledge_sources_manifest(payload: dict[str, Any], output_path: str | Path) -> dict[str, Any]:
    write_json(Path(output_path), payload)
    return payload


def export_knowledge_sources_report(report: str, output_path: str | Path) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return str(path)
