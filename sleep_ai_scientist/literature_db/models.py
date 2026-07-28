from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Literature Metadata schema."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class UpdateRun(TimestampMixin, Base):
    __tablename__ = "literature_update_runs"
    __table_args__ = (
        CheckConstraint(
            "run_type IN ('api_search', 'target_journal_scan', 'metadata_import', "
            "'weekly_update', 'schema_test')",
            name="ck_literature_update_runs_run_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'partial', 'failed')",
            name="ck_literature_update_runs_status",
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    run_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    query_name: Mapped[str | None] = mapped_column(String)
    query_text: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    error_summary: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )


class CandidateRecord(TimestampMixin, Base):
    __tablename__ = "literature_candidates"
    __table_args__ = (
        UniqueConstraint("candidate_key", name="uq_literature_candidates_candidate_key"),
        Index("ix_literature_candidates_source_name", "source_name"),
        Index("ix_literature_candidates_source_record_id", "source_record_id"),
        Index("ix_literature_candidates_run_id", "run_id"),
        Index("ix_literature_candidates_linked_paper_id", "linked_paper_id"),
        Index("ix_literature_candidates_payload_hash", "payload_hash"),
        Index("ix_literature_candidates_normalization_status", "normalization_status"),
        Index("ix_literature_candidates_dedup_status", "dedup_status"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    candidate_key: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_update_runs.run_id", ondelete="SET NULL"),
    )
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String)
    discovery_method: Mapped[str] = mapped_column(String, nullable=False)
    discovery_query: Mapped[str | None] = mapped_column(Text)
    target_journal_key: Mapped[str | None] = mapped_column(String)
    raw_title: Mapped[str | None] = mapped_column(Text)
    raw_abstract: Mapped[str | None] = mapped_column(Text)
    raw_doi: Mapped[str | None] = mapped_column(String)
    raw_pmid: Mapped[str | None] = mapped_column(String)
    raw_pmcid: Mapped[str | None] = mapped_column(String)
    raw_journal: Mapped[str | None] = mapped_column(Text)
    raw_authors: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    raw_publication_date: Mapped[str | None] = mapped_column(String)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    payload_hash: Mapped[str] = mapped_column(String, nullable=False)
    normalization_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    dedup_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    relevance_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    linked_paper_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("literature_papers.paper_id", ondelete="SET NULL")
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Paper(TimestampMixin, Base):
    __tablename__ = "literature_papers"
    __table_args__ = (
        CheckConstraint(
            "publication_year IS NULL OR publication_year BETWEEN 1600 AND 3000",
            name="ck_literature_papers_publication_year",
        ),
        Index("ix_literature_papers_normalized_title", "normalized_title"),
        Index("ix_literature_papers_publication_year", "publication_year"),
        Index("ix_literature_papers_normalized_journal_name", "normalized_journal_name"),
        Index("ix_literature_papers_first_author", "first_author"),
        Index("ix_literature_papers_is_retracted", "is_retracted"),
    )

    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    canonical_title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False)
    journal_name: Mapped[str | None] = mapped_column(Text)
    normalized_journal_name: Mapped[str | None] = mapped_column(Text)
    issn: Mapped[str | None] = mapped_column(String)
    eissn: Mapped[str | None] = mapped_column(String)
    publication_date: Mapped[date | None] = mapped_column(Date)
    publication_year: Mapped[int | None] = mapped_column(SmallInteger)
    volume: Mapped[str | None] = mapped_column(String)
    issue: Mapped[str | None] = mapped_column(String)
    pages: Mapped[str | None] = mapped_column(String)
    article_type: Mapped[str | None] = mapped_column(String)
    language: Mapped[str | None] = mapped_column(String)
    first_author: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    mesh_terms: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    publication_types: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    metadata_status: Mapped[str] = mapped_column(String, nullable=False)
    is_retracted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PaperAuthor(TimestampMixin, Base):
    __tablename__ = "literature_paper_authors"
    __table_args__ = (
        UniqueConstraint(
            "paper_id", "author_order", name="uq_literature_paper_authors_order"
        ),
        CheckConstraint("author_order >= 1", name="ck_literature_paper_authors_order"),
    )

    paper_author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_papers.paper_id", ondelete="CASCADE"),
        nullable=False,
    )
    author_order: Mapped[int] = mapped_column(Integer, nullable=False)
    given_name: Mapped[str | None] = mapped_column(Text)
    family_name: Mapped[str | None] = mapped_column(Text)
    initials: Mapped[str | None] = mapped_column(Text)
    collective_name: Mapped[str | None] = mapped_column(Text)
    orcid: Mapped[str | None] = mapped_column(String)
    affiliations: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    is_corresponding: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_name: Mapped[str | None] = mapped_column(String)
    raw_author: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )


class PaperIdentifier(Base):
    __tablename__ = "literature_paper_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "identifier_type", "normalized_value", name="uq_literature_identifier_global"
        ),
        UniqueConstraint(
            "paper_id",
            "identifier_type",
            "normalized_value",
            name="uq_literature_identifier_per_paper",
        ),
        CheckConstraint(
            "identifier_type IN ('doi', 'pmid', 'pmcid', 'semantic_scholar_id', "
            "'openalex_id', 'publisher_id')",
            name="ck_literature_identifier_type",
        ),
    )

    identifier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_papers.paper_id", ondelete="CASCADE"),
        nullable=False,
    )
    identifier_type: Mapped[str] = mapped_column(String, nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(String)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PaperSource(TimestampMixin, Base):
    __tablename__ = "literature_paper_sources"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_literature_paper_sources_candidate"),
        CheckConstraint(
            "match_score IS NULL OR (match_score >= 0.0 AND match_score <= 1.0)",
            name="ck_literature_paper_sources_match_score",
        ),
    )

    paper_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_papers.paper_id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String)
    discovery_method: Mapped[str] = mapped_column(String, nullable=False)
    match_method: Mapped[str] = mapped_column(String, nullable=False)
    match_score: Mapped[float | None] = mapped_column(Float)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AbstractVersion(TimestampMixin, Base):
    __tablename__ = "literature_abstract_versions"
    __table_args__ = (
        UniqueConstraint(
            "paper_id", "content_hash", name="uq_literature_abstract_versions_hash"
        ),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0.0 AND quality_score <= 1.0)",
            name="ck_literature_abstract_versions_quality_score",
        ),
        Index(
            "uq_literature_abstract_versions_preferred",
            "paper_id",
            unique=True,
            postgresql_where=text("is_preferred = true"),
        ),
    )

    abstract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_papers.paper_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    abstract_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String)
    is_structured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class DedupDecision(Base):
    __tablename__ = "literature_dedup_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('create_new', 'exact_match', 'fuzzy_match', 'version_relation', "
            "'manual_review', 'rejected', 'identifier_conflict')",
            name="ck_literature_dedup_decisions_decision",
        ),
        CheckConstraint(
            "match_score IS NULL OR (match_score >= 0.0 AND match_score <= 1.0)",
            name="ck_literature_dedup_decisions_match_score",
        ),
        Index(
            "uq_literature_dedup_decisions_current",
            "candidate_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )

    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
    )
    matched_paper_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("literature_papers.paper_id", ondelete="SET NULL")
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    match_method: Mapped[str] = mapped_column(String, nullable=False)
    match_score: Mapped[float | None] = mapped_column(Float)
    reasons: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PaperRelation(Base):
    __tablename__ = "literature_paper_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_paper_id",
            "target_paper_id",
            "relation_type",
            name="uq_literature_paper_relations_triplet",
        ),
        CheckConstraint(
            "source_paper_id <> target_paper_id",
            name="ck_literature_paper_relations_not_self",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_literature_paper_relations_confidence",
        ),
        CheckConstraint(
            "relation_type IN ('is_preprint_of', 'is_version_of', 'is_correction_of', "
            "'is_retraction_of', 'is_supplement_to', 'is_commentary_on')",
            name="ck_literature_paper_relations_type",
        ),
    )

    relation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    source_paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_papers.paper_id", ondelete="CASCADE"),
        nullable=False,
    )
    target_paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_papers.paper_id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    detection_method: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class JournalScanState(TimestampMixin, Base):
    __tablename__ = "literature_journal_scan_states"
    __table_args__ = (
        CheckConstraint(
            "consecutive_failure_count >= 0",
            name="ck_literature_journal_scan_states_failure_count",
        ),
        CheckConstraint(
            "status IN ('pending', 'resolving_url', 'profile_pending', 'profile_ready', "
            "'completed_with_relevant_papers', 'completed_no_relevant_papers', "
            "'completed_no_new_papers', 'partial', 'blocked_by_robots', "
            "'blocked_by_anti_bot', 'login_required', 'official_url_not_resolved', "
            "'listing_url_not_resolved', 'profile_broken', 'temporarily_failed', "
            "'permanently_failed', 'manual_review')",
            name="ck_literature_journal_scan_states_status",
        ),
    )

    journal_key: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False)
    issn: Mapped[str | None] = mapped_column(String)
    eissn: Mapped[str | None] = mapped_column(String)
    publisher: Mapped[str | None] = mapped_column(Text)
    identifier_quality: Mapped[str] = mapped_column(String, nullable=False)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_numbers: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_cursor: Mapped[str | None] = mapped_column(Text)
    last_seen_publication_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, nullable=False)
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    consecutive_failure_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )


class JournalURL(TimestampMixin, Base):
    __tablename__ = "literature_journal_urls"
    __table_args__ = (
        UniqueConstraint(
            "journal_key", "normalized_url", "url_type", name="uq_literature_journal_urls"
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_literature_journal_urls_confidence",
        ),
    )

    journal_url_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    journal_key: Mapped[str] = mapped_column(
        String,
        ForeignKey("literature_journal_scan_states.journal_key", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    url_type: Mapped[str] = mapped_column(String, nullable=False)
    resolution_source: Mapped[str] = mapped_column(String, nullable=False)
    resolution_method: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_http_status: Mapped[int | None] = mapped_column(Integer)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class JournalScraperProfile(TimestampMixin, Base):
    __tablename__ = "literature_journal_scraper_profiles"
    __table_args__ = (
        UniqueConstraint("journal_key", name="uq_literature_journal_scraper_profiles_key"),
        CheckConstraint(
            "verification_status IN ('verified', 'partial', 'manual_review', 'broken')",
            name="ck_literature_journal_scraper_profiles_verification",
        ),
    )

    scraper_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    journal_key: Mapped[str] = mapped_column(
        String,
        ForeignKey("literature_journal_scan_states.journal_key", ondelete="CASCADE"),
        nullable=False,
    )
    adapter_name: Mapped[str] = mapped_column(String, nullable=False)
    adapter_version: Mapped[str] = mapped_column(String, nullable=False)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    latest_articles_url: Mapped[str | None] = mapped_column(Text)
    current_issue_url: Mapped[str | None] = mapped_column(Text)
    archive_url: Mapped[str | None] = mapped_column(Text)
    search_url_template: Mapped[str | None] = mapped_column(Text)
    rss_url: Mapped[str | None] = mapped_column(Text)
    sitemap_url: Mapped[str | None] = mapped_column(Text)
    discovery_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    article_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    request_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verification_status: Mapped[str] = mapped_column(String, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_crawl_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class JournalCrawlRun(Base):
    __tablename__ = "literature_journal_crawl_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed_with_relevant_papers', "
            "'completed_no_relevant_papers', 'completed_no_new_papers', 'partial', "
            "'blocked_by_robots', 'blocked_by_anti_bot', 'login_required', "
            "'official_url_not_resolved', 'listing_url_not_resolved', 'profile_broken', "
            "'temporarily_failed', 'permanently_failed', 'manual_review')",
            name="ck_literature_journal_crawl_runs_status",
        ),
    )

    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    update_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_update_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    journal_key: Mapped[str] = mapped_column(
        String,
        ForeignKey("literature_journal_scan_states.journal_key", ondelete="CASCADE"),
        nullable=False,
    )
    scraper_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature_journal_scraper_profiles.scraper_profile_id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, nullable=False)
    listing_pages_requested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listing_pages_succeeded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    article_pages_requested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    article_pages_succeeded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    articles_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    articles_parsed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    articles_relevant: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    articles_uncertain: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    articles_excluded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    papers_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    papers_matched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    robots_status: Mapped[str | None] = mapped_column(String)
    http_status_counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    errors: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
