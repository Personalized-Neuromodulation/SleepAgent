from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.models import (
    AuditReport,
    BuildRun,
    Checkpoint,
    CorpusVersion,
    ClinicalTrial,
    DiagnosticTerm,
    Guideline,
    Instrument,
    ErrorLog,
    Paper,
    PaperSource,
    PublicDataset,
    Query,
    QueryResult,
    StandardRule,
    ToolMethod,
    utc_now,
)


def _empty_to_none(value: Any) -> Any:
    return None if value == "" else value


def _paper_payload(record: LiteratureRecord) -> dict[str, Any]:
    return {
        "paper_id": record.paper_id,
        "title": record.title,
        "abstract": _empty_to_none(record.abstract),
        "year": record.publication_year or record.year,
        "doi": _empty_to_none(record.doi),
        "pmid": _empty_to_none(record.pmid),
        "pmcid": _empty_to_none(getattr(record, "pmcid", None)),
        "journal": _empty_to_none(record.journal),
        "publication_type": _empty_to_none(record.publication_type),
        "authors_json": record.authors or [],
        "keywords_json": record.keywords or [],
        "mesh_terms_json": [],
        "citation_count": record.citation_count,
        "citation_source": record.citation_source,
        "citation_count_age_normalized": record.citation_count_age_normalized,
        "is_open_access": record.is_open_access,
        "open_access_url": None,
        "url": _empty_to_none(record.url),
        "source": _empty_to_none(record.source),
    }


class PaperRepository:
    def upsert_paper(self, session: Session, record: LiteratureRecord) -> Paper:
        payload = _paper_payload(record)
        paper = session.get(Paper, record.paper_id)
        if paper is None and payload.get("doi"):
            paper = self.get_by_doi(session, payload["doi"])
        if paper is None and payload.get("pmid"):
            paper = self.get_by_pmid(session, payload["pmid"])
        if paper is None:
            paper = Paper(**payload)
            session.add(paper)
            session.flush()
            return paper
        for key, value in payload.items():
            if key == "paper_id":
                continue
            if value not in (None, "", []) or getattr(paper, key) in (None, "", []):
                setattr(paper, key, value if value not in (None, "", []) else getattr(paper, key))
        paper.updated_at = utc_now()
        session.flush()
        return paper

    def get_by_paper_id(self, session: Session, paper_id: str) -> Paper | None:
        return session.get(Paper, paper_id)

    def get_by_doi(self, session: Session, doi: str) -> Paper | None:
        return session.scalar(select(Paper).where(Paper.doi == doi))

    def get_by_pmid(self, session: Session, pmid: str) -> Paper | None:
        return session.scalar(select(Paper).where(Paper.pmid == pmid))

    def get_by_pmcid(self, session: Session, pmcid: str) -> Paper | None:
        return session.scalar(select(Paper).where(Paper.pmcid == pmcid))

    def list_all(self, session: Session) -> list[Paper]:
        return list(session.scalars(select(Paper).order_by(Paper.paper_id)))

    def count(self, session: Session) -> int:
        return int(session.scalar(select(func.count()).select_from(Paper)) or 0)


class PaperSourceRepository:
    def add_source(self, session: Session, paper_id: str, **kwargs: Any) -> PaperSource:
        source = PaperSource(paper_id=paper_id, **kwargs)
        session.add(source)
        session.flush()
        return source

    def list_sources_for_paper(self, session: Session, paper_id: str) -> list[PaperSource]:
        return list(session.scalars(select(PaperSource).where(PaperSource.paper_id == paper_id).order_by(PaperSource.id)))


class QueryRepository:
    def upsert_query(self, session: Session, query_text: str, query_group: str, query_set_version: str, priority: float = 1.0, status: str = "active") -> Query:
        query_id = stable_id("query", query_set_version, query_group, query_text)
        query = session.get(Query, query_id)
        if query is None:
            query = Query(query_id=query_id, query_text=query_text, query_group=query_group, query_set_version=query_set_version, priority=priority, status=status)
            session.add(query)
        else:
            query.priority = priority
            query.status = status
            query.updated_at = utc_now()
        session.flush()
        return query

    def mark_query_status(self, session: Session, query_id: str, status: str) -> None:
        query = session.get(Query, query_id)
        if query:
            query.status = status
            query.updated_at = utc_now()
            session.flush()

    def list_active_queries(self, session: Session) -> list[Query]:
        return list(session.scalars(select(Query).where(Query.status == "active").order_by(Query.query_group, Query.query_text)))

    def list_by_query_set(self, session: Session, query_set_version: str) -> list[Query]:
        return list(session.scalars(select(Query).where(Query.query_set_version == query_set_version).order_by(Query.query_group, Query.query_text)))


class QueryResultRepository:
    def add_result(self, session: Session, query_id: str, provider: str, paper_id: str, rank: int | None = None, is_new_record: bool = False, duplicate_group_id: str | None = None) -> QueryResult:
        result = QueryResult(query_id=query_id, provider=provider, paper_id=paper_id, rank=rank, is_new_record=is_new_record, duplicate_group_id=duplicate_group_id)
        session.add(result)
        session.flush()
        return result

    def list_results_by_query(self, session: Session, query_id: str) -> list[QueryResult]:
        return list(session.scalars(select(QueryResult).where(QueryResult.query_id == query_id).order_by(QueryResult.rank, QueryResult.id)))

    def count_by_provider(self, session: Session) -> dict[str, int]:
        rows = session.execute(select(QueryResult.provider, func.count()).group_by(QueryResult.provider)).all()
        return {str(provider): int(count) for provider, count in rows}


class CorpusRepository:
    def create_or_update_corpus_version(self, session: Session, corpus_version: str, **kwargs: Any) -> CorpusVersion:
        corpus = session.get(CorpusVersion, corpus_version)
        if corpus is None:
            corpus = CorpusVersion(corpus_version=corpus_version, **kwargs)
            session.add(corpus)
        else:
            for key, value in kwargs.items():
                setattr(corpus, key, value)
        session.flush()
        return corpus

    def freeze_corpus(self, session: Session, corpus_version: str) -> None:
        corpus = session.get(CorpusVersion, corpus_version)
        if corpus:
            corpus.frozen = True
            session.flush()

    def get_corpus(self, session: Session, corpus_version: str) -> CorpusVersion | None:
        return session.get(CorpusVersion, corpus_version)


class RunRepository:
    def create_run(self, session: Session, run_type: str, config_path: str | None = None, query_config_path: str | None = None, corpus_version: str | None = None, run_id: str | None = None) -> BuildRun:
        run_id = run_id or stable_id("run", run_type, utc_now().isoformat())
        run = BuildRun(run_id=run_id, run_type=run_type, status="running", config_path=config_path, query_config_path=query_config_path, corpus_version=corpus_version, error_count=0, warning_count=0)
        session.add(run)
        session.flush()
        return run

    def finish_run(self, session: Session, run_id: str, status: str = "completed") -> None:
        run = session.get(BuildRun, run_id)
        if run:
            run.status = status
            run.finished_at = utc_now()
            session.flush()

    def update_run_status(self, session: Session, run_id: str, status: str) -> None:
        run = session.get(BuildRun, run_id)
        if run:
            run.status = status
            session.flush()

    def increment_error_count(self, session: Session, run_id: str) -> None:
        run = session.get(BuildRun, run_id)
        if run:
            run.error_count += 1
            session.flush()

    def increment_warning_count(self, session: Session, run_id: str) -> None:
        run = session.get(BuildRun, run_id)
        if run:
            run.warning_count += 1
            session.flush()


class CheckpointRepository:
    def add_checkpoint(self, session: Session, run_id: str, checkpoint_path: str, iteration: int | None = None, status: str = "completed", last_successful_stage: str | None = None, failed_stage: str | None = None, error_bundle_path: str | None = None, checkpoint_id: str | None = None) -> Checkpoint:
        checkpoint_id = checkpoint_id or stable_id("checkpoint", run_id, iteration, utc_now().isoformat())
        checkpoint = Checkpoint(checkpoint_id=checkpoint_id, run_id=run_id, iteration=iteration, status=status, checkpoint_path=checkpoint_path, last_successful_stage=last_successful_stage, failed_stage=failed_stage, error_bundle_path=error_bundle_path)
        session.add(checkpoint)
        session.flush()
        return checkpoint

    def get_latest_checkpoint(self, session: Session, run_id: str) -> Checkpoint | None:
        return session.scalar(select(Checkpoint).where(Checkpoint.run_id == run_id).order_by(Checkpoint.timestamp.desc()))


class AuditRepository:
    def add_audit_report(self, session: Session, audit_type: str, audit_json_path: str, passed: bool, run_id: str | None = None, corpus_version: str | None = None, warnings: list[Any] | None = None, errors: list[Any] | None = None, audit_id: str | None = None) -> AuditReport:
        audit_id = audit_id or stable_id("audit", audit_type, run_id or "", corpus_version or "", utc_now().isoformat())
        audit = AuditReport(audit_id=audit_id, run_id=run_id, corpus_version=corpus_version, audit_type=audit_type, audit_json_path=audit_json_path, passed=passed, warnings_json=warnings or [], errors_json=errors or [])
        session.add(audit)
        session.flush()
        return audit

    def list_audits(self, session: Session) -> list[AuditReport]:
        return list(session.scalars(select(AuditReport).order_by(AuditReport.created_at.desc())))


class ErrorRepository:
    def add_error(self, session: Session, message: str, stage: str | None = None, error_type: str | None = None, run_id: str | None = None, iteration: int | None = None, traceback_path: str | None = None, recoverable: bool = True, error_bundle_path: str | None = None, error_id: str | None = None) -> ErrorLog:
        error_id = error_id or stable_id("error", run_id or "", stage or "", message, utc_now().isoformat())
        log = ErrorLog(error_id=error_id, run_id=run_id, iteration=iteration, stage=stage, error_type=error_type, message=message, traceback_path=traceback_path, recoverable=recoverable, error_bundle_path=error_bundle_path, resolved=False)
        session.add(log)
        session.flush()
        return log

    def list_unresolved_errors(self, session: Session) -> list[ErrorLog]:
        return list(session.scalars(select(ErrorLog).where(ErrorLog.resolved.is_(False)).order_by(ErrorLog.timestamp.desc())))


class _DictRepository:
    model = None
    pk = ""
    order_by = ""

    def upsert(self, session: Session, payload: dict[str, Any]):
        key = payload[self.pk]
        item = session.get(self.model, key)
        if item is None:
            item = self.model(**payload)
            session.add(item)
        else:
            for field, value in payload.items():
                setattr(item, field, value)
        session.flush()
        return item

    def get(self, session: Session, key: str):
        return session.get(self.model, key)

    def list_all(self, session: Session):
        column = getattr(self.model, self.order_by or self.pk)
        return list(session.scalars(select(self.model).order_by(column)))

    def count(self, session: Session) -> int:
        return int(session.scalar(select(func.count()).select_from(self.model)) or 0)


class ClinicalTrialRepository(_DictRepository):
    model = ClinicalTrial
    pk = "trial_id"
    order_by = "nct_id"


class GuidelineRepository(_DictRepository):
    model = Guideline
    pk = "guideline_id"
    order_by = "title"


class StandardRuleRepository(_DictRepository):
    model = StandardRule
    pk = "standard_id"
    order_by = "rule_category"


class DiagnosticTermRepository(_DictRepository):
    model = DiagnosticTerm
    pk = "term_id"
    order_by = "category"


class DatasetRepository(_DictRepository):
    model = PublicDataset
    pk = "dataset_id"
    order_by = "name"


class InstrumentRepository(_DictRepository):
    model = Instrument
    pk = "instrument_id"
    order_by = "instrument_id"


class ToolMethodRepository(_DictRepository):
    model = ToolMethod
    pk = "tool_id"
    order_by = "tool_id"
