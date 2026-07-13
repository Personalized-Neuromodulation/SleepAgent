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
    DeduplicationEvent,
    DiagnosticTerm,
    Guideline,
    Instrument,
    ErrorLog,
    Paper,
    PaperAlias,
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
    from sleep_ai_scientist.literature.identity_resolution import compute_title_hash, normalize_doi, normalize_journal, normalize_pmcid, normalize_pmid, normalize_title

    doi = normalize_doi(record.doi)
    pmid = normalize_pmid(record.pmid)
    pmcid = normalize_pmcid(getattr(record, "pmcid", None))
    title_normalized = normalize_title(record.title)
    journal_normalized = normalize_journal(record.journal)
    return {
        "paper_id": record.paper_id,
        "canonical_paper_id": record.paper_id,
        "title": record.title,
        "title_normalized": title_normalized,
        "title_hash": compute_title_hash(record.title),
        "abstract": _empty_to_none(record.abstract),
        "year": record.publication_year or record.year,
        "doi": _empty_to_none(doi),
        "pmid": _empty_to_none(pmid),
        "pmcid": _empty_to_none(pmcid),
        "semantic_scholar_id": _empty_to_none(getattr(record, "semantic_scholar_id", None)),
        "openalex_id": _empty_to_none(getattr(record, "openalex_id", None)),
        "crossref_id": _empty_to_none(getattr(record, "crossref_id", None)),
        "journal": _empty_to_none(record.journal),
        "journal_normalized": _empty_to_none(journal_normalized),
        "first_author": _empty_to_none(getattr(record, "first_author", None) or (record.authors[0] if record.authors else None)),
        "publication_type": _empty_to_none(record.publication_type),
        "authors_json": record.authors or [],
        "keywords_json": record.keywords or [],
        "mesh_terms_json": [],
        "citation_count": record.citation_count,
        "citation_source": record.citation_source,
        "citation_sources_json": [record.citation_source] if record.citation_source else [],
        "citation_count_age_normalized": record.citation_count_age_normalized,
        "is_open_access": record.is_open_access,
        "open_access_url": _empty_to_none(getattr(record, "open_access_url", None)),
        "journal_priority_score": getattr(record, "journal_priority_score", None) or getattr(record, "journal_impact_factor", None),
        "journal_domain_json": [getattr(record, "journal_domain", None)] if getattr(record, "journal_domain", None) else [],
        "jcr_categories_json": [getattr(record, "jcr_category", None) or record.journal_quartile] if (getattr(record, "jcr_category", None) or record.journal_quartile) else [],
        "retrieval_channels_json": [record.retrieval_channel] if getattr(record, "retrieval_channel", None) else [],
        "source_providers_json": [record.provider or record.source] if (record.provider or record.source) else [],
        "duplicate_group_id": None,
        "merged_from_json": [],
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

    def find_by_alias(self, session: Session, alias_type: str, alias_value: str) -> Paper | None:
        alias = session.scalar(select(PaperAlias).where(PaperAlias.alias_type == alias_type, PaperAlias.alias_value == alias_value))
        return session.get(Paper, alias.paper_id) if alias else None

    def find_existing_by_identifiers(self, session: Session, record: LiteratureRecord) -> Paper | None:
        from sleep_ai_scientist.literature.identity_resolution import normalize_doi, normalize_pmcid, normalize_pmid

        identifiers = [
            ("doi", normalize_doi(record.doi)),
            ("pmid", normalize_pmid(record.pmid)),
            ("pmcid", normalize_pmcid(getattr(record, "pmcid", None))),
            ("semantic_scholar_id", getattr(record, "semantic_scholar_id", None)),
            ("openalex_id", getattr(record, "openalex_id", None)),
            ("crossref_id", getattr(record, "crossref_id", None)),
        ]
        for alias_type, value in identifiers:
            if not value:
                continue
            column = getattr(Paper, alias_type)
            paper = session.scalar(select(Paper).where(column == value))
            if paper:
                return paper
            paper = self.find_by_alias(session, alias_type, str(value))
            if paper:
                return paper
        return None

    def upsert_alias(self, session: Session, paper_id: str, alias_type: str, alias_value: str | None, provider: str | None = None) -> PaperAlias | None:
        if not alias_value:
            return None
        alias = session.scalar(select(PaperAlias).where(PaperAlias.alias_type == alias_type, PaperAlias.alias_value == str(alias_value)))
        if alias is None:
            alias = PaperAlias(paper_id=paper_id, alias_type=alias_type, alias_value=str(alias_value), provider=provider)
            session.add(alias)
        else:
            alias.paper_id = paper_id
            alias.provider = alias.provider or provider
        session.flush()
        return alias

    def update_retrieval_channels(self, session: Session, paper_id: str, channel: str | None) -> None:
        if not channel:
            return
        paper = session.get(Paper, paper_id)
        if paper is None:
            return
        channels = sorted(set((paper.retrieval_channels_json or []) + [channel]))
        paper.retrieval_channels_json = channels
        paper.updated_at = utc_now()
        session.flush()

    def update_source_providers(self, session: Session, paper_id: str, provider: str | None) -> None:
        if not provider:
            return
        paper = session.get(Paper, paper_id)
        if paper is None:
            return
        providers = sorted(set((paper.source_providers_json or []) + [provider]))
        paper.source_providers_json = providers
        paper.updated_at = utc_now()
        session.flush()

    def merge_into_existing(self, session: Session, existing_paper: Paper, incoming_record: LiteratureRecord) -> dict[str, Any]:
        from sleep_ai_scientist.literature.identity_resolution import merge_literature_records

        result = merge_literature_records(existing_paper, incoming_record)
        session.flush()
        return result

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


class DeduplicationRepository:
    def add_event(self, session: Session, **kwargs: Any) -> DeduplicationEvent:
        event = DeduplicationEvent(**kwargs)
        session.add(event)
        session.flush()
        return event

    def list_events(self, session: Session) -> list[DeduplicationEvent]:
        return list(session.scalars(select(DeduplicationEvent).order_by(DeduplicationEvent.event_id)))

    def export_report(self, session: Session) -> list[dict[str, Any]]:
        rows = []
        for event in self.list_events(session):
            rows.append({column.name: getattr(event, column.name) for column in DeduplicationEvent.__table__.columns})
        return rows


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
