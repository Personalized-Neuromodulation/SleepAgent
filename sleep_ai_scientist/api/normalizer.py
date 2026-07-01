from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.schemas.api import APILiteratureRecord
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def normalize_title(title: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (title or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def doi_key(doi: str | None) -> str:
    return (doi or "").lower().replace("https://doi.org/", "").strip()


def make_api_record(provider: str, provider_id: str | None, title: str, **kwargs: Any) -> APILiteratureRecord:
    doi = kwargs.get("doi")
    pmid = kwargs.get("pmid")
    key = doi_key(doi) or str(pmid or "").strip() or normalize_title(title)
    return APILiteratureRecord(
        provider=provider,
        provider_id=provider_id,
        paper_id=stable_id("api_paper", provider, key),
        title=title or "",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        **kwargs,
    )


def deduplicate_api_records(records: list[APILiteratureRecord]) -> list[APILiteratureRecord]:
    merged: dict[str, APILiteratureRecord] = {}
    providers: dict[str, set[str]] = {}
    for record in records:
        key = doi_key(record.doi) or (record.pmid or "").strip() or normalize_title(record.title)
        if not key:
            key = record.paper_id
        if key not in merged:
            merged[key] = record
            providers[key] = {record.provider}
            continue
        current = merged[key]
        providers[key].add(record.provider)
        current.abstract = current.abstract or record.abstract
        current.pmid = current.pmid or record.pmid
        current.pmcid = current.pmcid or record.pmcid
        current.doi = current.doi or record.doi
        current.url = current.url or record.url
        current.journal = current.journal or record.journal
        current.authors = current.authors or record.authors
        current.keywords = sorted(set(current.keywords + record.keywords))
        if record.citation_count is not None:
            current.citation_count = max(current.citation_count or 0, record.citation_count)
    for key, record in merged.items():
        record.source = "api:" + ",".join(sorted(providers[key]))
    return list(merged.values())


def api_to_literature_record(record: APILiteratureRecord) -> LiteratureRecord:
    return LiteratureRecord(
        paper_id=record.paper_id,
        title=record.title,
        abstract=record.abstract or "",
        year=record.year,
        doi=record.doi or "",
        pmid=record.pmid or "",
        source=record.source or f"api:{record.provider}",
        keywords=record.keywords,
        url=record.url or "",
        notes=f"provider={record.provider}; provider_id={record.provider_id or ''}; journal={record.journal or ''}",
    )


def deduplicate_literature(records: list[LiteratureRecord]) -> list[LiteratureRecord]:
    merged: dict[str, LiteratureRecord] = {}
    for record in records:
        key = doi_key(record.doi) or (record.pmid or "").strip() or normalize_title(record.title)
        if not key:
            key = record.paper_id
        if key not in merged:
            merged[key] = record
            continue
        current = merged[key]
        current.abstract = current.abstract or record.abstract
        current.source = ";".join(sorted(set(filter(None, [current.source, record.source]))))
        current.notes = ";".join(sorted(set(filter(None, [current.notes, record.notes]))))
    return list(merged.values())


def openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, indexes in inverted_index.items():
        for index in indexes:
            positions[int(index)] = word
    return " ".join(positions[index] for index in sorted(positions))
