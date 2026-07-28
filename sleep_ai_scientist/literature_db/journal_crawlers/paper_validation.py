from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

from ..normalization import normalize_issn, normalize_journal
from .models import CrawledPaperMetadata


_NON_PAPER_TITLES = (
    re.compile(r"^(editorial|advisory) board$", re.I),
    re.compile(r"^(erratum|corrigendum|correction|author correction|publisher correction|retraction|withdrawal|expression of concern|addendum)\b", re.I),
    re.compile(r"^(editorial|introduction|foreword|preface|masthead|front matter|back matter|index)$", re.I),
    re.compile(r"^(editorial|advisory board|letter to the editor|reply|response|commentary)\b", re.I),
    re.compile(r"(?:^|[.:]\s*)response to\b", re.I),
    re.compile(r"^(about|home|homepage|archive|all issues|current issue|latest articles)$", re.I),
    re.compile(r"^(author|submission) guidelines?$", re.I),
    re.compile(r"^(instructions for authors|information for authors)$", re.I),
    re.compile(r"^(table of contents|contents)$", re.I),
    re.compile(r"^.+,\s*volume\s+\d+,\s*issue\s+\d+$", re.I),
    re.compile(r"^.+\|\s*(cambridge core|springerlink|wiley online library)$", re.I),
    re.compile(r"^elsevier journal catalog:", re.I),
)
_NON_PAPER_TYPES = {
    "book",
    "book-chapter",
    "component",
    "dataset",
    "journal",
    "journal-issue",
    "journal-volume",
    "peer-review",
    "retraction",
    "correction",
    "reference-entry",
    "report",
    "webpage",
    "website",
}
_ARTICLE_TYPE_MARKERS = (
    "article",
    "review",
    "meta-analysis",
    "case report",
    "clinical trial",
)


@dataclass(frozen=True)
class PaperMetadataAssessment:
    is_paper: bool
    score: int
    reasons: list[str]
    evidence: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _raw_issns(raw: Any) -> set[str]:
    found: set[str] = set()

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                if "issn" in child_key.casefold():
                    visit(child, child_key)
                elif child_key in {"primary_location", "source", "host_venue"}:
                    visit(child, child_key)
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, str) and "issn" in key.casefold():
            normalized = normalize_issn(value)
            if normalized:
                found.add(normalized)

    visit(raw)
    return found


def _journal_matches(metadata: CrawledPaperMetadata, journal: Any) -> bool:
    expected_issns = {
        normalize_issn(value)
        for value in (getattr(journal, "issn", None), getattr(journal, "eissn", None))
        if value
    }
    if expected_issns & _raw_issns(metadata.raw_metadata):
        return True
    expected = normalize_journal(getattr(journal, "title", "") or "")
    actual = normalize_journal(metadata.journal or "")
    if not expected or not actual:
        return False
    if expected == actual or expected in actual or actual in expected:
        return True
    return SequenceMatcher(None, expected, actual).ratio() >= 0.72


def assess_paper_metadata(
    metadata: CrawledPaperMetadata, journal: Any
) -> PaperMetadataAssessment:
    title = " ".join((metadata.title or "").split())
    article_type = (metadata.article_type or "").strip().casefold()
    reasons: list[str] = []

    title_valid = len(title) >= 12 and not any(pattern.search(title) for pattern in _NON_PAPER_TITLES)
    if not title_valid:
        reasons.append("non_paper_or_missing_title")

    excluded_type = article_type in _NON_PAPER_TYPES
    article_type_valid = bool(article_type) and not excluded_type and any(
        marker in article_type for marker in _ARTICLE_TYPE_MARKERS
    )
    if excluded_type:
        reasons.append(f"excluded_type:{article_type}")

    raw_meta = metadata.raw_metadata.get("meta", {}) if isinstance(metadata.raw_metadata, dict) else {}
    citation_article_marker = bool(
        raw_meta.get("citation_title")
        and (
            raw_meta.get("citation_author")
            or raw_meta.get("citation_doi")
            or raw_meta.get("citation_publication_date")
        )
    )
    has_identifier = bool(metadata.doi or metadata.pmid or metadata.pmcid)
    has_authors = bool(metadata.authors)
    has_date = bool(metadata.publication_date)
    journal_match = _journal_matches(metadata, journal)
    core_evidence = sum((has_identifier, has_authors, has_date, journal_match))

    explicit_article = article_type_valid or citation_article_marker
    is_paper = bool(
        title_valid
        and not excluded_type
        and explicit_article
        and core_evidence >= 2
        and (has_identifier or has_authors)
    )
    if not explicit_article:
        reasons.append("no_article_level_schema_or_citation_metadata")
    if core_evidence < 2:
        reasons.append("insufficient_bibliographic_evidence")
    if not (has_identifier or has_authors):
        reasons.append("missing_identifier_and_authors")
    if not journal_match:
        reasons.append("journal_identity_not_confirmed")
    if is_paper:
        reasons.append("validated_scholarly_paper")

    evidence = {
        "title_valid": title_valid,
        "article_type_valid": article_type_valid,
        "citation_article_marker": citation_article_marker,
        "stable_identifier": has_identifier,
        "authors": has_authors,
        "publication_date": has_date,
        "journal_identity": journal_match,
    }
    return PaperMetadataAssessment(is_paper, core_evidence + int(explicit_article), reasons, evidence)
