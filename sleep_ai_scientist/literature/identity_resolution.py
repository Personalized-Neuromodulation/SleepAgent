from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sleep_ai_scientist.common.io import ensure_parent, write_csv, write_json
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.models import Paper, PaperSource, QueryResult, utc_now
from sleep_ai_scientist.storage.repositories import DeduplicationRepository, PaperRepository, PaperSourceRepository, QueryResultRepository

ALLOWED_RETRIEVAL_CHANNELS = {
    "api_broad",
    "journal_targeted",
    "citation_backward",
    "citation_forward",
    "query_expansion",
    "open_access_fulltext",
    "unknown",
}


@dataclass
class ResolutionResult:
    paper: Paper
    action: str
    matched_by: str
    match_score: float
    merged_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manual_review: dict[str, Any] | None = None


def normalize_doi(doi: str | None) -> str:
    value = str(doi or "").strip().lower()
    value = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.strip().rstrip(".")


def normalize_pmid(pmid: str | int | None) -> str:
    return "".join(re.findall(r"\d+", str(pmid or "")))


def normalize_pmcid(pmcid: str | int | None) -> str:
    value = str(pmcid or "").strip().upper()
    digits = "".join(re.findall(r"\d+", value))
    return f"PMC{digits}" if digits else ""


def normalize_title(title: str | None) -> str:
    value = str(title or "").lower()
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"_+", " ", value)
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def normalize_journal(journal: str | None) -> str:
    value = str(journal or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\b(the|journal|of)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def compute_title_hash(title: str | None) -> str:
    normalized = normalize_title(title)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _first_author(record: LiteratureRecord | Paper) -> str:
    value = getattr(record, "first_author", None)
    if value:
        return normalize_title(str(value))
    authors = getattr(record, "authors", None) or getattr(record, "authors_json", None) or []
    if authors:
        return normalize_title(str(authors[0]))
    return ""


def _record_year(record: LiteratureRecord | Paper) -> int | None:
    return getattr(record, "publication_year", None) or getattr(record, "year", None)


def compute_fingerprint(record: LiteratureRecord | Paper) -> dict[str, Any]:
    return {
        "doi": normalize_doi(getattr(record, "doi", None)),
        "pmid": normalize_pmid(getattr(record, "pmid", None)),
        "pmcid": normalize_pmcid(getattr(record, "pmcid", None)),
        "semantic_scholar_id": str(getattr(record, "semantic_scholar_id", "") or "").strip(),
        "openalex_id": _openalex_id(record),
        "crossref_id": str(getattr(record, "crossref_id", "") or "").strip(),
        "provider_id": str(getattr(record, "provider_id", "") or "").strip(),
        "url": str(getattr(record, "url", "") or "").strip(),
        "title_normalized": normalize_title(getattr(record, "title", None)),
        "title_hash": compute_title_hash(getattr(record, "title", None)),
        "journal_normalized": normalize_journal(getattr(record, "journal", None)),
        "year": _record_year(record),
        "first_author": _first_author(record),
    }


def assign_canonical_paper_id(record: LiteratureRecord | dict[str, Any]) -> str:
    getter = record.get if isinstance(record, dict) else lambda key, default=None: getattr(record, key, default)
    doi = normalize_doi(getter("doi", ""))
    if doi:
        return f"doi:{doi}"
    pmid = normalize_pmid(getter("pmid", ""))
    if pmid:
        return f"pmid:{pmid}"
    pmcid = normalize_pmcid(getter("pmcid", ""))
    if pmcid:
        return f"pmcid:{pmcid}"
    s2_id = str(getter("semantic_scholar_id", "") or "").strip()
    if s2_id:
        return f"s2:{s2_id}"
    openalex_id = _openalex_id(record)
    if openalex_id:
        return f"openalex:{openalex_id}"
    provider = str(getter("provider", "") or getter("source", "") or "").strip().lower()
    provider_id = str(getter("provider_id", "") or "").strip()
    if provider and provider_id:
        return f"{provider}:{provider_id}"
    title_hash = compute_title_hash(str(getter("title", "") or ""))
    return f"title:{title_hash}" if title_hash else f"title:{hashlib.sha1(json.dumps(dict(record) if isinstance(record, dict) else record.model_dump(mode='json'), sort_keys=True).encode('utf-8')).hexdigest()}"


def _openalex_id(record: LiteratureRecord | Paper | dict[str, Any]) -> str:
    getter = record.get if isinstance(record, dict) else lambda key, default=None: getattr(record, key, default)
    explicit = str(getter("openalex_id", "") or "").strip()
    if explicit:
        return explicit
    provider = str(getter("provider", "") or getter("source", "") or "").strip().lower()
    provider_id = str(getter("provider_id", "") or "").strip()
    if "openalex" in provider and provider_id:
        return provider_id.removeprefix("https://openalex.org/").strip("/")
    url = str(getter("url", "") or "").strip()
    match = re.search(r"openalex\.org/(W\d+)", url, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _provider(record: LiteratureRecord) -> str:
    return record.provider or record.source or "unknown"


def _channels(value: str | None) -> str:
    return value if value in ALLOWED_RETRIEVAL_CHANNELS else "unknown"


def _score_titles(a: str | None, b: str | None) -> float:
    left = normalize_title(a)
    right = normalize_title(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _values(record: LiteratureRecord) -> dict[str, Any]:
    fp = compute_fingerprint(record)
    return {
        **fp,
        "paper_id": assign_canonical_paper_id(record),
        "title": record.title,
        "abstract": record.abstract or None,
        "source": record.source or None,
        "provider": _provider(record),
        "provider_id": record.provider_id,
        "url": record.url or None,
        "publication_type": record.publication_type,
        "authors_json": record.authors or [],
        "keywords_json": record.keywords or [],
        "mesh_terms_json": [],
        "citation_count": record.citation_count,
        "citation_source": record.citation_source,
        "citation_sources_json": [record.citation_source] if record.citation_source else [],
        "citation_count_age_normalized": record.citation_count_age_normalized,
        "is_open_access": record.is_open_access,
        "open_access_url": getattr(record, "open_access_url", None),
        "journal_priority_score": getattr(record, "journal_priority_score", None) or getattr(record, "journal_impact_factor", None),
        "journal_domain_json": [record.journal_domain] if getattr(record, "journal_domain", None) else [],
        "jcr_categories_json": [record.jcr_category or record.journal_quartile] if (getattr(record, "jcr_category", None) or record.journal_quartile) else [],
        "retrieval_channels_json": [_channels(record.retrieval_channel)],
        "source_providers_json": [_provider(record)],
        "canonical_paper_id": assign_canonical_paper_id(record),
        "journal": record.journal,
        "first_author": getattr(record, "first_author", None) or (record.authors[0] if record.authors else None),
        "year": record.publication_year or record.year,
        "pmcid": fp["pmcid"] or None,
        "doi": fp["doi"] or None,
        "pmid": fp["pmid"] or None,
        "semantic_scholar_id": fp["semantic_scholar_id"] or None,
        "openalex_id": fp["openalex_id"] or None,
        "crossref_id": fp["crossref_id"] or None,
        "duplicate_group_id": None,
        "merged_from_json": [],
    }


def _nonempty(value: Any) -> bool:
    return value not in (None, "", [])


def _append_unique(values: list[Any] | None, incoming: list[Any] | None) -> list[Any]:
    result: list[Any] = []
    for value in (values or []) + (incoming or []):
        if value not in (None, "") and value not in result:
            result.append(value)
    return result


def _conflict(existing: Any, incoming: Any) -> bool:
    return _nonempty(existing) and _nonempty(incoming) and str(existing) != str(incoming)


def merge_literature_records(existing: Paper, incoming: LiteratureRecord) -> dict[str, Any]:
    values = _values(incoming)
    merged_fields: list[str] = []
    warnings: list[str] = []

    for field_name in ("doi", "pmid", "pmcid", "semantic_scholar_id", "openalex_id", "crossref_id"):
        current = getattr(existing, field_name)
        incoming_value = values[field_name]
        if not _nonempty(current) and _nonempty(incoming_value):
            setattr(existing, field_name, incoming_value)
            merged_fields.append(field_name)
        elif _conflict(current, incoming_value):
            warnings.append(f"{field_name}_conflict")

    title_score = _score_titles(existing.title, incoming.title)
    if title_score >= 0.94:
        pass
    elif len(incoming.title or "") > len(existing.title or ""):
        existing.title = incoming.title
        existing.title_normalized = values["title_normalized"]
        existing.title_hash = values["title_hash"]
        merged_fields.append("title")
    elif title_score < 0.85:
        warnings.append("title_conflict")

    if values["abstract"] and len(values["abstract"]) > len(existing.abstract or ""):
        existing.abstract = values["abstract"]
        merged_fields.append("abstract")

    if existing.year is None and values["year"] is not None:
        existing.year = values["year"]
        merged_fields.append("year")
    elif _conflict(existing.year, values["year"]):
        warnings.append("year_conflict")

    if not existing.journal and values["journal"]:
        existing.journal = values["journal"]
        existing.journal_normalized = values["journal_normalized"]
        merged_fields.append("journal")
    elif values["journal"] and len(values["journal"]) > len(existing.journal or ""):
        existing.journal = values["journal"]
        existing.journal_normalized = values["journal_normalized"]
        merged_fields.append("journal")

    if not existing.first_author and values["first_author"]:
        existing.first_author = values["first_author"]
        merged_fields.append("first_author")

    if values["citation_count"] is not None and (existing.citation_count is None or values["citation_count"] > existing.citation_count):
        existing.citation_count = values["citation_count"]
        existing.citation_source = values["citation_source"]
        merged_fields.append("citation_count")
    existing.citation_sources_json = _append_unique(existing.citation_sources_json, values["citation_sources_json"])

    if values["is_open_access"] is True and existing.is_open_access is not True:
        existing.is_open_access = True
        merged_fields.append("is_open_access")
    if not existing.open_access_url and values["open_access_url"]:
        existing.open_access_url = values["open_access_url"]
        merged_fields.append("open_access_url")

    if values["journal_priority_score"] is not None and (existing.journal_priority_score is None or values["journal_priority_score"] > existing.journal_priority_score):
        existing.journal_priority_score = values["journal_priority_score"]
        merged_fields.append("journal_priority_score")
    existing.journal_domain_json = _append_unique(existing.journal_domain_json, values["journal_domain_json"])
    existing.jcr_categories_json = _append_unique(existing.jcr_categories_json, values["jcr_categories_json"])
    existing.authors_json = _append_unique(existing.authors_json, values["authors_json"])
    existing.keywords_json = _append_unique(existing.keywords_json, values["keywords_json"])
    existing.mesh_terms_json = _append_unique(existing.mesh_terms_json, values["mesh_terms_json"])
    existing.retrieval_channels_json = sorted(set(_append_unique(existing.retrieval_channels_json, values["retrieval_channels_json"])))
    existing.source_providers_json = sorted(set(_append_unique(existing.source_providers_json, values["source_providers_json"])))
    existing.merged_from_json = _append_unique(existing.merged_from_json, [incoming.paper_id] if incoming.paper_id != existing.paper_id else [])
    existing.updated_at = utc_now()
    return {"merged_fields": merged_fields, "warnings": warnings}


def _match_by_identifiers(session: Session, fp: dict[str, Any]) -> tuple[Paper | None, str, float]:
    checks = [
        ("doi", fp["doi"]),
        ("pmid", fp["pmid"]),
        ("pmcid", fp["pmcid"]),
        ("semantic_scholar_id", fp["semantic_scholar_id"]),
        ("openalex_id", fp["openalex_id"]),
        ("crossref_id", fp["doi"] or fp["crossref_id"]),
        ("provider_id", fp["provider_id"]),
        ("url", fp["url"]),
    ]
    paper_repo = PaperRepository()
    for field_name, value in checks:
        if not value:
            continue
        if field_name == "provider_id":
            paper = None
        else:
            paper = session.scalar(select(Paper).where(getattr(Paper, field_name if field_name != "crossref_id" or fp["crossref_id"] else "doi") == value))
        if paper:
            return paper, field_name if field_name != "crossref_id" else "crossref_doi", 1.0
        alias = paper_repo.find_by_alias(session, field_name, str(value))
        if alias:
            return alias, f"{field_name}_alias", 1.0
    return None, "", 0.0


def _match_by_canonical_id(session: Session, record: LiteratureRecord) -> tuple[Paper | None, str, float]:
    canonical_id = assign_canonical_paper_id(record)
    if not canonical_id:
        return None, "", 0.0
    paper = session.scalar(select(Paper).where(or_(Paper.canonical_paper_id == canonical_id, Paper.paper_id == canonical_id)))
    if paper:
        return paper, "canonical_paper_id", 1.0
    return None, "", 0.0


def _match_by_title(session: Session, record: LiteratureRecord, fp: dict[str, Any]) -> tuple[Paper | None, str, float, dict[str, Any] | None]:
    if fp["title_hash"]:
        exact = session.scalar(select(Paper).where(Paper.title_hash == fp["title_hash"]))
        if exact:
            return exact, "normalized_title_exact", 1.0, None
    best: tuple[Paper | None, str, float] = (None, "", 0.0)
    manual: dict[str, Any] | None = None
    candidates = list(session.scalars(select(Paper).where(Paper.year == fp["year"]))) if fp["year"] else list(session.scalars(select(Paper)))
    for paper in candidates:
        score = _score_titles(paper.title, record.title)
        same_year = paper.year is not None and fp["year"] is not None and paper.year == fp["year"]
        same_journal = bool(paper.journal_normalized and fp["journal_normalized"] and paper.journal_normalized == fp["journal_normalized"])
        same_author = bool(_first_author(paper) and fp["first_author"] and _first_author(paper) == fp["first_author"])
        if same_year and score >= 0.94:
            candidate = (paper, "fuzzy_title_year", score)
        elif same_year and same_journal and score >= 0.90:
            candidate = (paper, "fuzzy_title_year_journal", score)
        elif same_year and same_author and score >= 0.90:
            candidate = (paper, "fuzzy_title_first_author_year", score)
        else:
            candidate = best
        if candidate[2] > best[2]:
            best = candidate
        if score >= 0.90 and same_year and same_journal and paper.doi and fp["doi"] and paper.doi != fp["doi"]:
            manual = _manual_review_row(paper, record, score, "doi_conflict_similar_title_journal_year")
        if 0.85 <= score < 0.94 and (manual is None or score > float(manual["match_score"])):
            manual = _manual_review_row(paper, record, score, "ambiguous_fuzzy_title")
        if score >= 0.94 and paper.year is not None and fp["year"] is not None and abs(paper.year - fp["year"]) > 1:
            manual = _manual_review_row(paper, record, score, "similar_title_year_conflict")
    return best[0], best[1], best[2], manual


def _manual_review_row(existing: Paper, incoming: LiteratureRecord, score: float, reason: str) -> dict[str, Any]:
    return {
        "candidate_group_id": f"manual:{existing.paper_id}:{incoming.paper_id}",
        "existing_paper_id": existing.paper_id,
        "incoming_temp_id": incoming.paper_id,
        "match_score": round(score, 4),
        "reason": reason,
        "existing_title": existing.title,
        "incoming_title": incoming.title,
        "existing_doi": existing.doi or "",
        "incoming_doi": normalize_doi(incoming.doi),
        "existing_pmid": existing.pmid or "",
        "incoming_pmid": normalize_pmid(incoming.pmid),
        "existing_year": existing.year or "",
        "incoming_year": incoming.publication_year or incoming.year or "",
        "existing_journal": existing.journal or "",
        "incoming_journal": incoming.journal or "",
        "suggested_action": "manual_review",
    }


def resolve_existing_paper(record: LiteratureRecord, session: Session) -> tuple[Paper | None, str, float, dict[str, Any] | None]:
    fp = compute_fingerprint(record)
    paper, matched_by, score = _match_by_canonical_id(session, record)
    if paper:
        return paper, matched_by, score, None
    paper, matched_by, score = _match_by_identifiers(session, fp)
    manual = None
    if paper:
        if paper.doi and normalize_doi(record.doi) and paper.doi != normalize_doi(record.doi):
            manual = _manual_review_row(paper, record, _score_titles(paper.title, record.title), "doi_conflict")
        if paper.pmid and normalize_pmid(record.pmid) and paper.pmid != normalize_pmid(record.pmid):
            manual = _manual_review_row(paper, record, _score_titles(paper.title, record.title), "pmid_conflict")
        return paper, matched_by, score, manual
    return _match_by_title(session, record, fp)


def _insert_paper(session: Session, record: LiteratureRecord, retrieval_channel: str) -> Paper:
    values = _values(record)
    values["retrieval_channels_json"] = [retrieval_channel]
    record.paper_id = values["paper_id"]
    record.retrieval_channel = retrieval_channel
    paper_columns = {column.name for column in Paper.__table__.columns}
    paper = Paper(**{key: value for key, value in values.items() if key in paper_columns})
    session.add(paper)
    session.flush()
    _upsert_aliases(session, paper.paper_id, record)
    return paper


def _upsert_aliases(session: Session, paper_id: str, record: LiteratureRecord) -> None:
    repo = PaperRepository()
    provider = _provider(record)
    fp = compute_fingerprint(record)
    for alias_type in ("doi", "pmid", "pmcid", "semantic_scholar_id", "openalex_id", "crossref_id", "title_hash"):
        repo.upsert_alias(session, paper_id, alias_type, fp.get(alias_type), provider=provider)
    if record.provider_id:
        repo.upsert_alias(session, paper_id, "provider_id", record.provider_id, provider=provider)


def _add_source(session: Session, paper_id: str, record: LiteratureRecord, retrieval_channel: str, query_set_version: str | None = None) -> None:
    PaperSourceRepository().add_source(
        session,
        paper_id,
        provider=_provider(record),
        provider_id=record.provider_id,
        query_text=getattr(record, "query", None),
        query_group=getattr(record, "query_group", None),
        query_set_version=query_set_version or getattr(record, "query_set_version", None),
        retrieval_channel=retrieval_channel,
        retrieved_at=utc_now(),
        raw_json=record.model_dump(mode="json"),
    )


def _add_query_result(
    session: Session,
    paper_id: str,
    record: LiteratureRecord,
    retrieval_channel: str,
    is_new_record: bool,
    query_lookup: dict[str, Any] | None = None,
    rank: int | None = None,
) -> None:
    query_text = getattr(record, "query", None)
    if not query_text or not query_lookup or query_text not in query_lookup:
        return
    query = query_lookup[query_text]
    QueryResultRepository().add_result(
        session,
        query.query_id,
        _provider(record),
        paper_id,
        rank=rank,
        is_new_record=is_new_record,
        duplicate_group_id=getattr(session.get(Paper, paper_id), "duplicate_group_id", None),
    )


def _add_event(
    session: Session,
    paper: Paper | None,
    record: LiteratureRecord,
    matched_by: str,
    score: float,
    action: str,
    retrieval_channel: str,
    notes: str | None = None,
) -> None:
    DeduplicationRepository().add_event(
        session,
        canonical_paper_id=paper.paper_id if paper else None,
        incoming_paper_id=record.paper_id,
        matched_by=matched_by,
        match_score=score,
        action=action,
        existing_title=paper.title if paper else None,
        incoming_title=record.title,
        existing_doi=paper.doi if paper else None,
        incoming_doi=normalize_doi(record.doi),
        existing_pmid=paper.pmid if paper else None,
        incoming_pmid=normalize_pmid(record.pmid),
        existing_journal=paper.journal if paper else None,
        incoming_journal=record.journal,
        existing_year=paper.year if paper else None,
        incoming_year=record.publication_year or record.year,
        retrieval_channel=retrieval_channel,
        provider=_provider(record),
        notes=notes,
    )


def resolve_and_upsert(
    record: LiteratureRecord,
    session: Session,
    *,
    retrieval_channel: str = "unknown",
    query_lookup: dict[str, Any] | None = None,
    query_set_version: str | None = None,
    rank: int | None = None,
) -> ResolutionResult:
    retrieval_channel = _channels(retrieval_channel or getattr(record, "retrieval_channel", None))
    record.retrieval_channel = retrieval_channel
    incoming_original_id = record.paper_id
    existing, matched_by, score, manual = resolve_existing_paper(record, session)
    if existing is None:
        record.paper_id = assign_canonical_paper_id(record)
        existing = _find_by_final_canonical_id(session, record.paper_id)
        if existing is not None:
            merge_result = merge_literature_records(existing, record)
            PaperRepository().update_retrieval_channels(session, existing.paper_id, retrieval_channel)
            PaperRepository().update_source_providers(session, existing.paper_id, _provider(record))
            _upsert_aliases(session, existing.paper_id, record)
            _add_source(session, existing.paper_id, record, retrieval_channel, query_set_version=query_set_version)
            _add_query_result(session, existing.paper_id, record, retrieval_channel, False, query_lookup, rank)
            _add_event(
                session,
                existing,
                record,
                "canonical_paper_id_preinsert",
                1.0,
                "merged_into_existing",
                retrieval_channel,
                notes=";".join(merge_result["warnings"]),
            )
            session.flush()
            return ResolutionResult(
                paper=existing,
                action="merged_into_existing",
                matched_by="canonical_paper_id_preinsert",
                match_score=1.0,
                merged_fields=merge_result["merged_fields"],
                warnings=merge_result["warnings"],
            )
        paper = _insert_paper(session, record, retrieval_channel)
        _add_source(session, paper.paper_id, record, retrieval_channel, query_set_version=query_set_version)
        _add_query_result(session, paper.paper_id, record, retrieval_channel, True, query_lookup, rank)
        _add_event(session, paper, record, "new_record", 1.0, "inserted_new", retrieval_channel)
        return ResolutionResult(paper=paper, action="inserted_new", matched_by="new_record", match_score=1.0)

    record.paper_id = incoming_original_id
    merge_result = merge_literature_records(existing, record)
    PaperRepository().update_retrieval_channels(session, existing.paper_id, retrieval_channel)
    PaperRepository().update_source_providers(session, existing.paper_id, _provider(record))
    _upsert_aliases(session, existing.paper_id, record)
    _add_source(session, existing.paper_id, record, retrieval_channel, query_set_version=query_set_version)
    _add_query_result(session, existing.paper_id, record, retrieval_channel, False, query_lookup, rank)
    action = "manual_review_needed" if manual else "merged_into_existing"
    _add_event(session, existing, record, matched_by, score, action, retrieval_channel, notes=";".join(merge_result["warnings"]))
    session.flush()
    return ResolutionResult(
        paper=existing,
        action=action,
        matched_by=matched_by,
        match_score=score,
        merged_fields=merge_result["merged_fields"],
        warnings=merge_result["warnings"],
        manual_review=manual,
    )


def _find_by_final_canonical_id(session: Session, canonical_id: str | None) -> Paper | None:
    if not canonical_id:
        return None
    return session.scalar(select(Paper).where(or_(Paper.canonical_paper_id == canonical_id, Paper.paper_id == canonical_id)))


def deduplicate_records(records: list[LiteratureRecord]) -> tuple[list[LiteratureRecord], list[dict[str, Any]], list[dict[str, Any]]]:
    canonical: list[LiteratureRecord] = []
    report: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    for record in records:
        record.paper_id = assign_canonical_paper_id(record)
        existing = None
        matched_by = "new_record"
        score = 1.0
        for candidate in canonical:
            candidate_fp = compute_fingerprint(candidate)
            incoming_fp = compute_fingerprint(record)
            for key in ("doi", "pmid", "pmcid", "semantic_scholar_id", "openalex_id"):
                if candidate_fp[key] and candidate_fp[key] == incoming_fp[key]:
                    existing, matched_by, score = candidate, key, 1.0
                    break
            if existing:
                break
            if candidate_fp["title_hash"] and candidate_fp["title_hash"] == incoming_fp["title_hash"]:
                existing, matched_by, score = candidate, "normalized_title_exact", 1.0
                break
            title_score = _score_titles(candidate.title, record.title)
            same_year = candidate_fp["year"] is not None and candidate_fp["year"] == incoming_fp["year"]
            same_journal = candidate_fp["journal_normalized"] and candidate_fp["journal_normalized"] == incoming_fp["journal_normalized"]
            same_author = candidate_fp["first_author"] and candidate_fp["first_author"] == incoming_fp["first_author"]
            if same_year and (title_score >= 0.94 or (title_score >= 0.90 and (same_journal or same_author))):
                existing, matched_by, score = candidate, "fuzzy_title", title_score
                break
            if 0.85 <= title_score < 0.94:
                manual_review.append(
                    {
                        "candidate_group_id": f"manual:{candidate.paper_id}:{record.paper_id}",
                        "existing_paper_id": candidate.paper_id,
                        "incoming_temp_id": record.paper_id,
                        "match_score": round(title_score, 4),
                        "reason": "ambiguous_fuzzy_title",
                        "existing_title": candidate.title,
                        "incoming_title": record.title,
                        "existing_doi": candidate.doi,
                        "incoming_doi": record.doi,
                        "existing_pmid": candidate.pmid,
                        "incoming_pmid": record.pmid,
                        "existing_year": candidate.year,
                        "incoming_year": record.year,
                        "existing_journal": candidate.journal,
                        "incoming_journal": record.journal,
                        "suggested_action": "manual_review",
                    }
                )
        if existing is None:
            canonical.append(record)
            action = "inserted_new"
        else:
            _merge_record_objects(existing, record)
            action = "merged_into_existing"
        report.append(_report_row(existing or record, record, matched_by, score, action, [], []))
    return canonical, report, manual_review


def _merge_record_objects(existing: LiteratureRecord, incoming: LiteratureRecord) -> None:
    existing.source = ";".join(sorted(set(filter(None, [existing.source, incoming.source]))))
    existing.provider = ";".join(sorted(set(filter(None, [existing.provider, incoming.provider])))) or existing.provider
    existing.keywords = sorted(set(existing.keywords + incoming.keywords))
    existing.authors = _append_unique(existing.authors, incoming.authors)
    if incoming.abstract and len(incoming.abstract) > len(existing.abstract or ""):
        existing.abstract = incoming.abstract
    for field_name in ("doi", "pmid", "pmcid", "journal", "publication_type", "url"):
        if not getattr(existing, field_name, None) and getattr(incoming, field_name, None):
            setattr(existing, field_name, getattr(incoming, field_name))
    if existing.citation_count is None or (incoming.citation_count is not None and incoming.citation_count > existing.citation_count):
        existing.citation_count = incoming.citation_count
        existing.citation_source = incoming.citation_source
    if incoming.journal_priority_score is not None and (existing.journal_priority_score is None or incoming.journal_priority_score > existing.journal_priority_score):
        existing.journal_priority_score = incoming.journal_priority_score


def _report_row(paper: Paper | LiteratureRecord, incoming: LiteratureRecord, matched_by: str, score: float, action: str, merged_fields: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "duplicate_group_id": getattr(paper, "duplicate_group_id", None) or "",
        "canonical_paper_id": getattr(paper, "paper_id", ""),
        "incoming_paper_id": incoming.paper_id,
        "matched_by": matched_by,
        "match_score": round(score, 4),
        "action": action,
        "existing_provider_sources": json.dumps(getattr(paper, "source_providers_json", None) or [], ensure_ascii=False),
        "incoming_provider": _provider(incoming),
        "existing_retrieval_channels": json.dumps(getattr(paper, "retrieval_channels_json", None) or [], ensure_ascii=False),
        "incoming_retrieval_channel": incoming.retrieval_channel or "",
        "title": getattr(paper, "title", ""),
        "doi": getattr(paper, "doi", "") or "",
        "pmid": getattr(paper, "pmid", "") or "",
        "pmcid": getattr(paper, "pmcid", "") or "",
        "journal": getattr(paper, "journal", "") or "",
        "year": getattr(paper, "year", "") or "",
        "merged_fields": ";".join(merged_fields),
        "warnings": ";".join(warnings),
    }


def write_deduplication_report(rows: list[dict[str, Any]], output_path: str | Path) -> None:
    write_csv(Path(output_path), rows)


def write_manual_review(rows: list[dict[str, Any]], output_path: str | Path) -> None:
    write_csv(Path(output_path), rows)


def export_deduplication_artifacts(
    session: Session,
    report_path: str | Path,
    summary_path: str | Path,
    manual_review_path: str | Path,
) -> dict[str, Any]:
    events = list(DeduplicationRepository().list_events(session))
    report_rows = []
    for event in events:
        paper = session.get(Paper, event.canonical_paper_id) if event.canonical_paper_id else None
        incoming = LiteratureRecord(
            paper_id=event.incoming_paper_id or "",
            title=event.incoming_title or "",
            doi=event.incoming_doi or "",
            pmid=event.incoming_pmid or "",
            journal=event.incoming_journal,
            year=event.incoming_year,
            provider=event.provider,
            retrieval_channel=event.retrieval_channel,
        )
        report_rows.append(_report_row(paper or incoming, incoming, event.matched_by or "", event.match_score or 0.0, event.action, [], (event.notes or "").split(";") if event.notes else []))
    write_deduplication_report(report_rows, report_path)
    manual_rows = [
        {
            "candidate_group_id": f"manual:{event.canonical_paper_id}:{event.incoming_paper_id}",
            "existing_paper_id": event.canonical_paper_id or "",
            "incoming_temp_id": event.incoming_paper_id or "",
            "match_score": event.match_score or "",
            "reason": event.notes or event.matched_by or "manual_review_needed",
            "existing_title": event.existing_title or "",
            "incoming_title": event.incoming_title or "",
            "existing_doi": event.existing_doi or "",
            "incoming_doi": event.incoming_doi or "",
            "existing_pmid": event.existing_pmid or "",
            "incoming_pmid": event.incoming_pmid or "",
            "existing_year": event.existing_year or "",
            "incoming_year": event.incoming_year or "",
            "existing_journal": event.existing_journal or "",
            "incoming_journal": event.incoming_journal or "",
            "suggested_action": "manual_review",
        }
        for event in events
        if event.action == "manual_review_needed"
    ]
    write_manual_review(manual_rows, manual_review_path)
    summary = build_deduplication_summary(session, events)
    write_json(Path(summary_path), summary)
    return {"report_rows": len(report_rows), "manual_review_rows": len(manual_rows), "summary": summary}


def build_deduplication_summary(session: Session, events: list[Any] | None = None) -> dict[str, Any]:
    events = events if events is not None else list(DeduplicationRepository().list_events(session))
    total = len(events)
    papers = list(session.scalars(select(Paper)))
    source_rows = list(session.scalars(select(PaperSource)))
    inserted = sum(1 for event in events if event.action == "inserted_new")
    merged = sum(1 for event in events if event.action == "merged_into_existing")
    skipped = sum(1 for event in events if event.action == "skipped_duplicate")
    manual = sum(1 for event in events if event.action == "manual_review_needed")
    api_papers = {source.paper_id for source in source_rows if source.retrieval_channel == "api_broad"}
    targeted_papers = {source.paper_id for source in source_rows if source.retrieval_channel == "journal_targeted"}
    return {
        "total_incoming_records": total,
        "inserted_new_count": inserted,
        "merged_duplicate_count": merged,
        "skipped_duplicate_count": skipped,
        "manual_review_count": manual,
        "doi_match_count": sum(1 for event in events if event.matched_by in {"doi", "crossref_doi", "doi_alias"}),
        "pmid_match_count": sum(1 for event in events if event.matched_by in {"pmid", "pmid_alias"}),
        "pmcid_match_count": sum(1 for event in events if event.matched_by in {"pmcid", "pmcid_alias"}),
        "title_exact_match_count": sum(1 for event in events if event.matched_by == "normalized_title_exact"),
        "fuzzy_match_count": sum(1 for event in events if str(event.matched_by or "").startswith("fuzzy_title")),
        "conflict_count": sum(1 for event in events if event.notes),
        "records_with_multiple_sources": sum(1 for paper in papers if len(paper.sources) > 1),
        "records_from_api_broad": len(api_papers),
        "records_from_journal_targeted": len(targeted_papers),
        "overlap_api_broad_and_journal_targeted": len(api_papers & targeted_papers),
        "duplicate_rate": round((merged + skipped + manual) / total, 6) if total else 0.0,
    }
