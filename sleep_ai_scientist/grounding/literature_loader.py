from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_csv, read_json, read_yaml
from sleep_ai_scientist.common.utils import split_keywords, stable_id
from sleep_ai_scientist.schemas.literature import LiteratureRecord


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
    """Normalize loose metadata into the Phase 1 LiteratureRecord schema."""
    title = str(row.get("title") or "").strip()
    abstract = str(row.get("abstract") or "").strip()
    year_raw = row.get("year") or None
    year = int(year_raw) if str(year_raw or "").strip().isdigit() else None
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
    )


def load_literature(path: str | Path) -> list[LiteratureRecord]:
    """Public loader used by the grounding pipeline and tests."""
    source = Path(path)
    return [normalize_literature_row(row) for row in _rows_from_path(source)]
