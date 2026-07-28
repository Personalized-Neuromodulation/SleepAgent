from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class StrictInput(BaseModel):
    model_config = {"extra": "forbid"}


class UpdateRunCreate(StrictInput):
    run_type: str
    status: str = "pending"
    started_at: datetime | None = None
    query_name: str | None = None
    query_text: str | None = None
    config_snapshot: dict[str, Any] = Field(default_factory=dict)


class CandidateCreate(StrictInput):
    source_name: str
    source_record_id: str | None = None
    discovery_method: str
    discovery_query: str | None = None
    target_journal_key: str | None = None
    raw_title: str | None = None
    raw_abstract: str | None = None
    raw_doi: str | None = None
    raw_pmid: str | None = None
    raw_pmcid: str | None = None
    raw_journal: str | None = None
    raw_authors: list[Any] = Field(default_factory=list)
    raw_publication_date: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    normalization_status: str = "pending"
    dedup_status: str = "pending"
    relevance_status: str = "pending"
    discovered_at: datetime | None = None
    retrieved_at: datetime | None = None


class PaperCreate(StrictInput):
    canonical_title: str
    journal_name: str | None = None
    issn: str | None = None
    eissn: str | None = None
    publication_date: date | str | None = None
    publication_year: int | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    article_type: str | None = None
    language: str | None = None
    first_author: str | None = None
    keywords: list[Any] = Field(default_factory=list)
    mesh_terms: list[Any] = Field(default_factory=list)
    publication_types: list[Any] = Field(default_factory=list)
    metadata_status: str = "canonical"
    is_retracted: bool = False


class PaperAuthorCreate(StrictInput):
    author_order: int
    given_name: str | None = None
    family_name: str | None = None
    initials: str | None = None
    collective_name: str | None = None
    orcid: str | None = None
    affiliations: list[Any] = Field(default_factory=list)
    is_corresponding: bool = False
    source_name: str | None = None
    raw_author: dict[str, Any] = Field(default_factory=dict)


class IdentifierCreate(StrictInput):
    identifier_type: str
    raw_value: str
    source_name: str | None = None
    is_primary: bool = False


class PaperSourceCreate(StrictInput):
    source_name: str
    source_record_id: str | None = None
    discovery_method: str
    match_method: str
    match_score: float | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class AbstractVersionCreate(StrictInput):
    source_name: str
    abstract_text: str
    language: str | None = None
    is_structured: bool = False
    quality_score: float | None = None
    fetched_at: datetime | None = None


class DedupDecisionCreate(StrictInput):
    decision: str
    match_method: str
    match_score: float | None = None
    reasons: list[Any] = Field(default_factory=list)
    requires_manual_review: bool = False
    is_current: bool = True


class PaperRelationCreate(StrictInput):
    relation_type: str
    confidence: float | None = None
    detection_method: str | None = None


class JournalScanStateCreate(StrictInput):
    journal_key: str
    title: str
    normalized_title: str
    issn: str | None = None
    eissn: str | None = None
    publisher: str | None = None
    identifier_quality: str
    source_file: str
    source_row_numbers: list[Any] = Field(default_factory=list)
    last_attempted_at: datetime | None = None
    last_successful_scan_at: datetime | None = None
    last_cursor: str | None = None
    last_seen_publication_date: date | None = None
    status: str
    last_error: dict[str, Any] | None = None
    consecutive_failure_count: int = 0


class JournalURLCreate(StrictInput):
    url: str
    normalized_url: str
    url_type: str
    resolution_source: str
    resolution_method: str
    confidence: float | None = None
    is_official: bool = False
    is_active: bool = True
    requires_manual_review: bool = False
    last_http_status: int | None = None
    last_verified_at: datetime | None = None
    last_error: dict[str, Any] | None = None


class JournalScraperProfileCreate(StrictInput):
    adapter_name: str
    adapter_version: str = "1"
    homepage_url: str | None = None
    latest_articles_url: str | None = None
    current_issue_url: str | None = None
    archive_url: str | None = None
    search_url_template: str | None = None
    rss_url: str | None = None
    sitemap_url: str | None = None
    discovery_rules: dict[str, Any] = Field(default_factory=dict)
    article_rules: dict[str, Any] = Field(default_factory=dict)
    request_policy: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    verification_status: str
    last_verified_at: datetime | None = None
    last_successful_crawl_at: datetime | None = None
    last_error: dict[str, Any] | None = None


# Transitional input name retained for local metadata fixtures; it does not expose IDs.
CandidateInput = CandidateCreate
