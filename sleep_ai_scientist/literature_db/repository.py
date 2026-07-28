from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .deduplication import IdentifierConflictError
from .models import (
    AbstractVersion,
    CandidateRecord,
    DedupDecision,
    JournalScanState,
    JournalCrawlRun,
    JournalScraperProfile,
    JournalURL,
    Paper,
    PaperAuthor,
    PaperIdentifier,
    PaperRelation,
    PaperSource,
    UpdateRun,
    utcnow,
)
from .normalization import (
    normalize_date,
    normalize_doi,
    normalize_issn,
    normalize_journal,
    normalize_pmcid,
    normalize_pmid,
    normalize_title,
)
from .schemas import (
    AbstractVersionCreate,
    CandidateCreate,
    DedupDecisionCreate,
    IdentifierCreate,
    JournalScanStateCreate,
    JournalScraperProfileCreate,
    JournalURLCreate,
    PaperAuthorCreate,
    PaperCreate,
    PaperRelationCreate,
    PaperSourceCreate,
    UpdateRunCreate,
)


SUPPORTED_IDENTIFIER_TYPES = {
    "doi",
    "pmid",
    "pmcid",
    "semantic_scholar_id",
    "openalex_id",
    "publisher_id",
}


def _payload_hash(payload: dict[str, Any]) -> str:
    value = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_identifier(identifier_type: str, value: str) -> str:
    kind = identifier_type.strip().lower()
    if kind not in SUPPORTED_IDENTIFIER_TYPES:
        raise ValueError(f"Unsupported identifier type: {identifier_type}")
    if kind == "doi":
        normalized = normalize_doi(value)
    elif kind == "pmid":
        normalized = normalize_pmid(value)
    elif kind == "pmcid":
        normalized = normalize_pmcid(value)
    else:
        normalized = value.strip()
    if not normalized:
        raise ValueError(f"Invalid {kind} identifier: {value!r}")
    return normalized


class LiteratureRepository:
    """Transaction-friendly repository for canonical Literature metadata."""

    def create_update_run(self, session: Session, data: UpdateRunCreate) -> UpdateRun:
        values = data.model_dump(exclude_none=True)
        run = UpdateRun(**values)
        session.add(run)
        session.flush()
        return run

    def complete_update_run(
        self,
        session: Session,
        run: UpdateRun,
        *,
        status: str = "completed",
        counts: dict[str, Any] | None = None,
        error_summary: list[Any] | None = None,
    ) -> UpdateRun:
        run.status = status
        run.completed_at = utcnow()
        if counts is not None:
            run.counts = counts
        if error_summary is not None:
            run.error_summary = error_summary
        session.flush()
        return run

    def create_candidate(
        self,
        session: Session,
        data: CandidateCreate,
        *,
        run: UpdateRun | None = None,
    ) -> CandidateRecord:
        raw = data.model_dump(mode="json", exclude_none=True)
        payload = data.raw_payload or raw
        payload_hash = _payload_hash(payload)
        natural_value = data.source_record_id or payload_hash
        candidate_key = f"{data.source_name.strip().lower()}|{natural_value}"
        existing = self.get_candidate_by_key(session, candidate_key)
        if existing is not None:
            existing.retrieved_at = utcnow()
            session.flush()
            return existing
        values = data.model_dump(exclude_none=True)
        values["source_name"] = data.source_name.strip().lower()
        values["candidate_key"] = candidate_key
        values["payload_hash"] = payload_hash
        values["raw_payload"] = payload
        if run is not None:
            values["run_id"] = run.run_id
        candidate = CandidateRecord(**values)
        session.add(candidate)
        session.flush()
        return candidate

    def get_candidate_by_key(
        self, session: Session, candidate_key: str
    ) -> CandidateRecord | None:
        return session.scalar(
            select(CandidateRecord).where(CandidateRecord.candidate_key == candidate_key)
        )

    def create_canonical_paper(self, session: Session, data: PaperCreate) -> Paper:
        title = data.canonical_title.strip()
        normalized_title = normalize_title(title)
        if not title or not normalized_title:
            raise ValueError("canonical_title must not be empty")
        publication_date = normalize_date(data.publication_date)
        publication_year = data.publication_year or (
            publication_date.year if publication_date else None
        )
        paper = Paper(
            canonical_title=title,
            normalized_title=normalized_title,
            journal_name=data.journal_name,
            normalized_journal_name=(
                normalize_journal(data.journal_name) if data.journal_name else None
            ),
            issn=normalize_issn(data.issn),
            eissn=normalize_issn(data.eissn),
            publication_date=publication_date,
            publication_year=publication_year,
            volume=data.volume,
            issue=data.issue,
            pages=data.pages,
            article_type=data.article_type,
            language=data.language,
            first_author=data.first_author,
            keywords=data.keywords,
            mesh_terms=data.mesh_terms,
            publication_types=data.publication_types,
            metadata_status=data.metadata_status,
            is_retracted=data.is_retracted,
        )
        session.add(paper)
        session.flush()
        return paper

    def get_paper_by_id(self, session: Session, paper_id: uuid.UUID) -> Paper | None:
        return session.get(Paper, paper_id)

    def replace_paper_authors(
        self,
        session: Session,
        paper: Paper,
        authors: Iterable[PaperAuthorCreate],
    ) -> list[PaperAuthor]:
        author_values = list(authors)
        orders = [author.author_order for author in author_values]
        if any(order < 1 for order in orders):
            raise ValueError("author_order must start at 1")
        if len(orders) != len(set(orders)):
            raise ValueError("author_order must be unique within a paper")
        session.execute(delete(PaperAuthor).where(PaperAuthor.paper_id == paper.paper_id))
        session.flush()
        rows = [
            PaperAuthor(paper_id=paper.paper_id, **author.model_dump(exclude_none=True))
            for author in author_values
        ]
        session.add_all(rows)
        if rows:
            first = rows[0]
            paper.first_author = first.collective_name or " ".join(
                part for part in (first.given_name, first.family_name) if part
            ) or None
        session.flush()
        return rows

    def add_identifier(
        self,
        session: Session,
        paper: Paper,
        data: IdentifierCreate,
    ) -> PaperIdentifier:
        kind = data.identifier_type.strip().lower()
        normalized = _normalize_identifier(kind, data.raw_value)
        existing = session.scalar(
            select(PaperIdentifier).where(
                PaperIdentifier.identifier_type == kind,
                PaperIdentifier.normalized_value == normalized,
            )
        )
        if existing is not None:
            if existing.paper_id == paper.paper_id:
                return existing
            raise IdentifierConflictError(
                {kind: {"existing_paper_id": str(existing.paper_id), "requested_paper_id": str(paper.paper_id)}}
            )
        identifier = PaperIdentifier(
            paper_id=paper.paper_id,
            identifier_type=kind,
            raw_value=data.raw_value,
            normalized_value=normalized,
            source_name=data.source_name,
            is_primary=data.is_primary,
        )
        session.add(identifier)
        session.flush()
        return identifier

    def find_paper_by_identifier(
        self, session: Session, identifier_type: str, value: str
    ) -> Paper | None:
        kind = identifier_type.strip().lower()
        normalized = _normalize_identifier(kind, value)
        identifier = session.scalar(
            select(PaperIdentifier).where(
                PaperIdentifier.identifier_type == kind,
                PaperIdentifier.normalized_value == normalized,
            )
        )
        return session.get(Paper, identifier.paper_id) if identifier else None

    def add_paper_source(
        self,
        session: Session,
        paper: Paper,
        candidate: CandidateRecord,
        data: PaperSourceCreate,
    ) -> PaperSource:
        existing = session.scalar(
            select(PaperSource).where(PaperSource.candidate_id == candidate.candidate_id)
        )
        if existing is not None:
            if existing.paper_id != paper.paper_id:
                raise ValueError("Candidate is already linked to another canonical paper")
            existing.last_seen_at = data.last_seen_at or utcnow()
            session.flush()
            return existing
        source = PaperSource(
            paper_id=paper.paper_id,
            candidate_id=candidate.candidate_id,
            **data.model_dump(exclude_none=True),
        )
        candidate.linked_paper_id = paper.paper_id
        session.add(source)
        session.flush()
        return source

    def add_abstract_version(
        self,
        session: Session,
        paper: Paper,
        data: AbstractVersionCreate,
    ) -> AbstractVersion:
        abstract_text = data.abstract_text.strip()
        if not abstract_text:
            raise ValueError("abstract_text must not be empty")
        content_hash = hashlib.sha256(abstract_text.encode("utf-8")).hexdigest()
        existing = session.scalar(
            select(AbstractVersion).where(
                AbstractVersion.paper_id == paper.paper_id,
                AbstractVersion.content_hash == content_hash,
            )
        )
        if existing is not None:
            return existing
        abstract = AbstractVersion(
            paper_id=paper.paper_id,
            content_hash=content_hash,
            **data.model_dump(exclude_none=True),
        )
        session.add(abstract)
        session.flush()
        return abstract

    def set_preferred_abstract(
        self, session: Session, paper: Paper, abstract: AbstractVersion
    ) -> AbstractVersion:
        if abstract.paper_id != paper.paper_id:
            raise ValueError("Abstract does not belong to the requested paper")
        session.execute(
            update(AbstractVersion)
            .where(
                AbstractVersion.paper_id == paper.paper_id,
                AbstractVersion.is_preferred.is_(True),
            )
            .values(is_preferred=False, updated_at=utcnow())
        )
        session.flush()
        abstract.is_preferred = True
        abstract.updated_at = utcnow()
        session.flush()
        return abstract

    def record_dedup_decision(
        self,
        session: Session,
        candidate: CandidateRecord,
        data: DedupDecisionCreate,
        *,
        matched_paper: Paper | None = None,
    ) -> DedupDecision:
        if data.is_current:
            session.execute(
                update(DedupDecision)
                .where(
                    DedupDecision.candidate_id == candidate.candidate_id,
                    DedupDecision.is_current.is_(True),
                )
                .values(is_current=False)
            )
            session.flush()
        decision = DedupDecision(
            candidate_id=candidate.candidate_id,
            matched_paper_id=matched_paper.paper_id if matched_paper else None,
            **data.model_dump(),
        )
        session.add(decision)
        session.flush()
        return decision

    def add_paper_relation(
        self,
        session: Session,
        source_paper: Paper,
        target_paper: Paper,
        data: PaperRelationCreate,
    ) -> PaperRelation:
        if source_paper.paper_id == target_paper.paper_id:
            raise ValueError("A paper cannot have a relation to itself")
        existing = session.scalar(
            select(PaperRelation).where(
                PaperRelation.source_paper_id == source_paper.paper_id,
                PaperRelation.target_paper_id == target_paper.paper_id,
                PaperRelation.relation_type == data.relation_type,
            )
        )
        if existing is not None:
            return existing
        relation = PaperRelation(
            source_paper_id=source_paper.paper_id,
            target_paper_id=target_paper.paper_id,
            **data.model_dump(exclude_none=True),
        )
        session.add(relation)
        session.flush()
        return relation

    def upsert_journal_scan_state(
        self, session: Session, data: JournalScanStateCreate
    ) -> JournalScanState:
        state = session.get(JournalScanState, data.journal_key)
        values = data.model_dump(exclude={"journal_key"})
        if state is None:
            state = JournalScanState(journal_key=data.journal_key, **values)
            session.add(state)
        else:
            for key, value in values.items():
                setattr(state, key, value)
            state.updated_at = utcnow()
        session.flush()
        return state

    def upsert_journal_url(
        self, session: Session, journal_key: str, data: JournalURLCreate
    ) -> JournalURL:
        row = session.scalar(
            select(JournalURL).where(
                JournalURL.journal_key == journal_key,
                JournalURL.normalized_url == data.normalized_url,
                JournalURL.url_type == data.url_type,
            )
        )
        values = data.model_dump()
        if row is None:
            row = JournalURL(journal_key=journal_key, **values)
            session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        session.flush()
        return row

    def upsert_scraper_profile(
        self,
        session: Session,
        journal_key: str,
        data: JournalScraperProfileCreate,
        *,
        preserve_manual_rules: bool = True,
    ) -> JournalScraperProfile:
        row = session.scalar(
            select(JournalScraperProfile).where(
                JournalScraperProfile.journal_key == journal_key
            )
        )
        values = data.model_dump()
        if row is None:
            row = JournalScraperProfile(journal_key=journal_key, **values)
            session.add(row)
        else:
            if preserve_manual_rules and row.discovery_rules.get("manual_override"):
                values["discovery_rules"] = row.discovery_rules
            if preserve_manual_rules and row.article_rules.get("manual_override"):
                values["article_rules"] = row.article_rules
            for key, value in values.items():
                setattr(row, key, value)
        session.flush()
        return row

    def row_counts(self, session: Session) -> dict[str, int]:
        models = (
            UpdateRun,
            CandidateRecord,
            Paper,
            PaperAuthor,
            PaperIdentifier,
            PaperSource,
            AbstractVersion,
            DedupDecision,
            PaperRelation,
            JournalScanState,
            JournalCrawlRun,
            JournalURL,
            JournalScraperProfile,
        )
        return {
            model.__tablename__: session.scalar(select(func.count()).select_from(model)) or 0
            for model in models
        }
