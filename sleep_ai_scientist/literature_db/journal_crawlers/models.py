from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ResolvedJournalURL:
    url: str
    url_type: str
    resolution_source: str
    resolution_method: str
    confidence: float
    is_official: bool
    http_status: int | None = None
    requires_manual_review: bool = False
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScraperProfileData:
    journal_key: str
    title: str
    publisher: str | None
    adapter_name: str
    adapter_version: str = "1"
    verification_status: str = "manual_review"
    enabled: bool = False
    homepage_url: str | None = None
    latest_articles_url: str | None = None
    current_issue_url: str | None = None
    archive_url: str | None = None
    search_url_template: str | None = None
    rss_url: str | None = None
    sitemap_url: str | None = None
    discovery_rules: dict[str, Any] = field(default_factory=dict)
    article_rules: dict[str, Any] = field(default_factory=dict)
    request_policy: dict[str, Any] = field(default_factory=dict)
    last_error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CrawledPaperMetadata:
    source_url: str
    title: str
    authors: list[dict[str, Any]] = field(default_factory=list)
    abstract: str | None = None
    journal: str | None = None
    publication_date: str | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    article_type: str | None = None
    language: str | None = None
    keywords: list[str] = field(default_factory=list)
    subject_headings: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    discovery_channel: str = "web_crawl"
    discovery_provider: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
