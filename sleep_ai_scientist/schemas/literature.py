from __future__ import annotations

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class LiteratureRecord(BaseModel):
    paper_id: str
    title: str
    abstract: str = ""
    year: int | None = None
    doi: str = ""
    pmid: str = ""
    source: str = ""
    keywords: list[str] = Field(default_factory=list)
    url: str = ""
    notes: str = ""
    journal: str | None = None
    publication_year: int | None = None
    publication_type: str | None = None
    authors: list[str] = Field(default_factory=list)
    citation_count: int | None = None
    citation_source: str | None = None
    citation_count_age_normalized: float | None = None
    journal_impact_factor: float | None = None
    journal_impact_factor_year: int | None = None
    journal_quartile: str | None = None
    journal_metric_source: str | None = None
    is_open_access: bool | None = None
    provider: str | None = None
    provider_id: str | None = None
    pmcid: str | None = None
    semantic_scholar_id: str | None = None
    openalex_id: str | None = None
    crossref_id: str | None = None
    first_author: str | None = None
    retrieval_channel: str | None = None
    query: str | None = None
    query_group: str | None = None
    query_set_version: str | None = None
    journal_priority_score: float | None = None
    journal_domain: str | None = None
    jcr_category: str | None = None
    open_access_url: str | None = None


class LiteratureCollection(BaseModel):
    records: list[LiteratureRecord] = Field(default_factory=list)
