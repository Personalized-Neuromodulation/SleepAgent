from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_csv, read_json, read_yaml
from sleep_ai_scientist.common.utils import split_keywords, stable_id
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def _to_int(value: Any) -> int | None:
    return int(value) if str(value or "").strip().isdigit() else None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _rows_from_path(path: Path) -> list[dict[str, Any]]:
    """Load raw literature rows from local CSV/JSON/YAML metadata files."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv(path)
    if suffix == ".json":
        payload = read_json(path)
        return payload if isinstance(payload, list) else payload.get("records", [])
    if suffix in {".yaml", ".yml"}:
        payload = read_yaml(path)
        return payload if isinstance(payload, list) else payload.get("records", [])
    raise ValueError(f"Unsupported literature format: {path}")


def normalize_literature_row(row: dict[str, Any]) -> LiteratureRecord:
    """Normalize loose metadata into the grounding LiteratureRecord schema."""
    title = str(row.get("title") or "").strip()
    abstract = str(row.get("abstract") or "").strip()
    year = _to_int(row.get("publication_year") or row.get("year"))
    # Stable generated IDs make toy and ad hoc seed files reproducible even
    # when paper_id is omitted by the user.
    paper_id = str(row.get("paper_id") or "").strip() or stable_id("paper", title, abstract, year)
    return LiteratureRecord(
        paper_id=paper_id,
        title=title,
        abstract=abstract,
        year=year,
        doi=str(row.get("doi") or "").strip(),
        pmid=str(row.get("pmid") or "").strip(),
        source=str(row.get("source") or "").strip(),
        keywords=split_keywords(row.get("keywords")),
        url=str(row.get("url") or "").strip(),
        notes=str(row.get("notes") or "").strip(),
        journal=str(row.get("journal") or "").strip() or None,
        publication_year=_to_int(row.get("publication_year") or year),
        publication_type=str(row.get("publication_type") or "").strip() or None,
        authors=split_keywords(row.get("authors")),
        citation_count=_to_int(row.get("citation_count")),
        citation_source=str(row.get("citation_source") or "").strip() or None,
        citation_count_age_normalized=_to_float(row.get("citation_count_age_normalized")),
        journal_impact_factor=_to_float(row.get("journal_impact_factor")),
        journal_impact_factor_year=_to_int(row.get("journal_impact_factor_year")),
        journal_quartile=str(row.get("journal_quartile") or "").strip() or None,
        journal_metric_source=str(row.get("journal_metric_source") or "").strip() or None,
        is_open_access=_to_bool(row.get("is_open_access")),
        provider=str(row.get("provider") or "").strip() or None,
        provider_id=str(row.get("provider_id") or "").strip() or None,
    )


def load_literature(path: str | Path) -> list[LiteratureRecord]:
    """Public loader used by the grounding pipeline and tests."""
    source = Path(path)
    return [normalize_literature_row(row) for row in _rows_from_path(source)]
