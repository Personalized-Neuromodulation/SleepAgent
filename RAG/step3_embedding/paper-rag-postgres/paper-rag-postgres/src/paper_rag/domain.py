from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


@dataclass(slots=True)
class SourcePaper:
    title: str
    doi: str
    journal_type: str
    journal: str
    file_path: Path
    source: str
    downloaded_at: str
    source_csv: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedSection:
    title: str
    section_type: str
    order: int
    text: str
    page_start: int | None = None
    page_end: int | None = None
    parent_title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedAsset:
    asset_type: str
    label: str
    caption: str
    page: int | None = None
    content: str | None = None


@dataclass(slots=True)
class ParsedDocument:
    title: str
    abstract: str
    sections: list[ParsedSection]
    assets: list[ParsedAsset] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    parser_name: str = "unknown"
    parser_version: str = "1"
    quality: str = "medium"
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    chunk_id: UUID
    section_order: int
    level: str
    index: int
    text: str
    token_count: int
    text_hash: str
    section_type: str
    section_title: str
    page_start: int | None
    page_end: int | None
    parent_chunk_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(cls, **kwargs: Any) -> "Chunk":
        return cls(chunk_id=uuid4(), **kwargs)

