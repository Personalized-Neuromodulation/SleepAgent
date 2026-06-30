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


class LiteratureCollection(BaseModel):
    records: list[LiteratureRecord] = Field(default_factory=list)
