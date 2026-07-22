from __future__ import annotations

from enum import Enum

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class LiteratureAPIProvider(str, Enum):
    pubmed = "pubmed"
    europe_pmc = "europe_pmc"
    openalex = "openalex"
    semantic_scholar = "semantic_scholar"


class APISearchQuery(BaseModel):
    query: str
    provider: str | None = None
    max_results: int = 20
    year_from: int | None = None
    year_to: int | None = None


class APILiteratureRecord(BaseModel):
    provider: str
    provider_id: str | None = None
    paper_id: str
    title: str
    abstract: str | None = None
    year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    url: str | None = None
    source: str | None = None
    journal: str | None = None
    publication_year: int | None = None
    publication_type: str | None = None
    authors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    citation_count: int | None = None
    citation_source: str | None = None
    citation_count_age_normalized: float | None = None
    journal_impact_factor: float | None = None
    journal_impact_factor_year: int | None = None
    journal_quartile: str | None = None
    journal_metric_source: str | None = None
    is_open_access: bool | None = None
    retrieved_at: str
    query: str = ""
    raw_source_available: bool = False
    raw: dict | None = None


class APISearchResult(BaseModel):
    provider: str
    query: str
    count: int
    records: list[APILiteratureRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class APICallLog(BaseModel):
    provider: str
    endpoint: str
    query: str | None = None
    status_code: int | None = None
    success: bool
    elapsed_seconds: float | None = None
    cached: bool = False
    error: str | None = None
    timestamp: str
