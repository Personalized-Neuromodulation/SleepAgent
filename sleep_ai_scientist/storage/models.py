from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class JSONAuto(JSON):
    """Use JSONB on PostgreSQL and JSON on SQLite."""

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class Paper(Base):
    __tablename__ = "papers"

    paper_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    doi: Mapped[str | None] = mapped_column(String(512), unique=True, index=True)
    pmid: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    pmcid: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    journal: Mapped[str | None] = mapped_column(Text)
    publication_type: Mapped[str | None] = mapped_column(String(128))
    authors_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    keywords_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    mesh_terms_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    citation_count: Mapped[int | None] = mapped_column(Integer)
    citation_source: Mapped[str | None] = mapped_column(String(128))
    citation_count_age_normalized: Mapped[float | None] = mapped_column(Float)
    is_open_access: Mapped[bool | None] = mapped_column(Boolean)
    open_access_url: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    sources: Mapped[list["PaperSource"]] = relationship(back_populates="paper")


class PaperSource(Base):
    __tablename__ = "paper_sources"
    __table_args__ = (Index("ix_paper_sources_provider_query", "provider", "query_group"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.paper_id"), index=True)
    provider: Mapped[str | None] = mapped_column(String(128), index=True)
    provider_id: Mapped[str | None] = mapped_column(String(256), index=True)
    query_text: Mapped[str | None] = mapped_column(Text)
    query_group: Mapped[str | None] = mapped_column(String(256), index=True)
    query_set_version: Mapped[str | None] = mapped_column(String(256), index=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONAuto)

    paper: Mapped[Paper] = relationship(back_populates="sources")


class Query(Base):
    __tablename__ = "queries"
    __table_args__ = (
        UniqueConstraint("query_text", "query_group", "query_set_version", name="uq_queries_text_group_version"),
        Index("ix_queries_group_version", "query_group", "query_set_version"),
    )

    query_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_group: Mapped[str] = mapped_column(String(256), nullable=False)
    query_set_version: Mapped[str] = mapped_column(String(256), nullable=False)
    priority: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(64), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class QueryResult(Base):
    __tablename__ = "query_results"
    __table_args__ = (Index("ix_query_results_query_provider", "query_id", "provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.query_id"), index=True)
    provider: Mapped[str] = mapped_column(String(128), index=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.paper_id"), index=True)
    rank: Mapped[int | None] = mapped_column(Integer)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    is_new_record: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_group_id: Mapped[str | None] = mapped_column(String(128))


class CorpusVersion(Base):
    __tablename__ = "corpus_versions"

    corpus_version: Mapped[str] = mapped_column(String(256), primary_key=True)
    library_version: Mapped[str | None] = mapped_column(String(256))
    query_set_version: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    manifest_path: Mapped[str | None] = mapped_column(Text)
    registry_csv_path: Mapped[str | None] = mapped_column(Text)
    registry_jsonl_path: Mapped[str | None] = mapped_column(Text)
    report_path: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class BuildRun(Base):
    __tablename__ = "build_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_type: Mapped[str] = mapped_column(String(128), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(64), index=True)
    config_path: Mapped[str | None] = mapped_column(Text)
    query_config_path: Mapped[str | None] = mapped_column(Text)
    corpus_version: Mapped[str | None] = mapped_column(String(256), index=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)


class Checkpoint(Base):
    __tablename__ = "checkpoints"
    __table_args__ = (Index("ix_checkpoints_run_iteration", "run_id", "iteration"),)

    checkpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("build_runs.run_id"), index=True)
    iteration: Mapped[int | None] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    status: Mapped[str] = mapped_column(String(64))
    checkpoint_path: Mapped[str] = mapped_column(Text)
    last_successful_stage: Mapped[str | None] = mapped_column(String(256))
    failed_stage: Mapped[str | None] = mapped_column(String(256))
    error_bundle_path: Mapped[str | None] = mapped_column(Text)


class AuditReport(Base):
    __tablename__ = "audit_reports"

    audit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("build_runs.run_id"), index=True)
    corpus_version: Mapped[str | None] = mapped_column(String(256), index=True)
    audit_type: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    audit_json_path: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    errors_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)


class ErrorLog(Base):
    __tablename__ = "error_logs"
    __table_args__ = (Index("ix_error_logs_run_stage", "run_id", "stage"),)

    error_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(128), index=True)
    iteration: Mapped[int | None] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    stage: Mapped[str | None] = mapped_column(String(256), index=True)
    error_type: Mapped[str | None] = mapped_column(String(256))
    message: Mapped[str] = mapped_column(Text)
    traceback_path: Mapped[str | None] = mapped_column(Text)
    recoverable: Mapped[bool] = mapped_column(Boolean, default=True)
    error_bundle_path: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class ClinicalTrial(Base):
    __tablename__ = "clinical_trials"

    trial_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    nct_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    brief_title: Mapped[str | None] = mapped_column(Text)
    official_title: Mapped[str | None] = mapped_column(Text)
    conditions_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    interventions_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    intervention_types_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    phase: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(128), index=True)
    study_type: Mapped[str | None] = mapped_column(String(128))
    allocation: Mapped[str | None] = mapped_column(String(128))
    masking: Mapped[str | None] = mapped_column(String(128))
    primary_purpose: Mapped[str | None] = mapped_column(String(128))
    start_date: Mapped[str | None] = mapped_column(String(64))
    completion_date: Mapped[str | None] = mapped_column(String(64))
    enrollment: Mapped[int | None] = mapped_column(Integer)
    enrollment_type: Mapped[str | None] = mapped_column(String(128))
    primary_outcomes_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    secondary_outcomes_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    eligibility_json: Mapped[dict[str, Any] | None] = mapped_column(JSONAuto)
    minimum_age: Mapped[str | None] = mapped_column(String(128))
    maximum_age: Mapped[str | None] = mapped_column(String(128))
    sex: Mapped[str | None] = mapped_column(String(64))
    locations_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    sponsor: Mapped[str | None] = mapped_column(Text)
    collaborators_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    source_url: Mapped[str | None] = mapped_column(Text)
    query_text: Mapped[str | None] = mapped_column(Text)
    query_group: Mapped[str | None] = mapped_column(String(256), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONAuto)


class Guideline(Base):
    __tablename__ = "guidelines"

    guideline_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    organization: Mapped[str | None] = mapped_column(Text, index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    topic: Mapped[str | None] = mapped_column(String(256), index=True)
    population: Mapped[str | None] = mapped_column(Text)
    condition: Mapped[str | None] = mapped_column(Text)
    intervention: Mapped[str | None] = mapped_column(Text)
    recommendation_summary: Mapped[str | None] = mapped_column(Text)
    recommendations_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    recommendation_strength: Mapped[str | None] = mapped_column(String(128))
    evidence_certainty: Mapped[str | None] = mapped_column(String(128))
    methodology: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(512), index=True)
    pmid: Mapped[str | None] = mapped_column(String(64), index=True)
    access_status: Mapped[str | None] = mapped_column(String(128))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    notes: Mapped[str | None] = mapped_column(Text)


class StandardRule(Base):
    __tablename__ = "standards_rules"

    standard_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    organization: Mapped[str | None] = mapped_column(Text, index=True)
    version: Mapped[str | None] = mapped_column(String(64))
    year: Mapped[int | None] = mapped_column(Integer)
    topic: Mapped[str | None] = mapped_column(String(256))
    rule_category: Mapped[str | None] = mapped_column(String(256), index=True)
    rule_summary: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    access_status: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)


class DiagnosticTerm(Base):
    __tablename__ = "diagnostic_terms"

    term_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str | None] = mapped_column(Text)
    term: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(256), index=True)
    parent_term: Mapped[str | None] = mapped_column(Text)
    synonyms_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    definition: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(String(128))
    downstream_relevance_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    notes: Mapped[str | None] = mapped_column(Text)


class PublicDataset(Base):
    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, index=True)
    url: Mapped[str | None] = mapped_column(Text)
    modality_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    population: Mapped[str | None] = mapped_column(Text)
    species: Mapped[str | None] = mapped_column(String(128))
    sample_size: Mapped[int | None] = mapped_column(Integer)
    labels_available: Mapped[bool | None] = mapped_column(Boolean)
    sleep_staging_available: Mapped[bool | None] = mapped_column(Boolean)
    psg_available: Mapped[bool | None] = mapped_column(Boolean)
    eeg_available: Mapped[bool | None] = mapped_column(Boolean)
    fmri_available: Mapped[bool | None] = mapped_column(Boolean)
    dti_available: Mapped[bool | None] = mapped_column(Boolean)
    mri_available: Mapped[bool | None] = mapped_column(Boolean)
    scales_available: Mapped[bool | None] = mapped_column(Boolean)
    access_status: Mapped[str | None] = mapped_column(String(128), index=True)
    license: Mapped[str | None] = mapped_column(Text)
    benchmark_tasks_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    notes: Mapped[str | None] = mapped_column(Text)


class Instrument(Base):
    __tablename__ = "instruments"

    instrument_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    abbreviation: Mapped[str | None] = mapped_column(String(128), index=True)
    domain: Mapped[str | None] = mapped_column(Text, index=True)
    score_range: Mapped[str | None] = mapped_column(String(128))
    direction: Mapped[str | None] = mapped_column(Text)
    cutoffs_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    license_status: Mapped[str | None] = mapped_column(String(128))
    reference: Mapped[str | None] = mapped_column(Text)
    role_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    notes: Mapped[str | None] = mapped_column(Text)


class ToolMethod(Base):
    __tablename__ = "tools_methods"

    tool_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, index=True)
    modality: Mapped[str | None] = mapped_column(String(128), index=True)
    role_json: Mapped[list[Any] | None] = mapped_column(JSONAuto)
    source_url: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
