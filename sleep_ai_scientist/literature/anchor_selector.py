from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_csv
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def _score(record: LiteratureRecord, query_group: str, coverage_gap: bool = False) -> float:
    text = " ".join([record.title or "", record.abstract or "", " ".join(record.keywords or [])]).lower()
    mechanism = 1.0 if any(term in text for term in ["spindle", "slow wave", "orexin", "gaba", "adenosine", "thalam"]) else 0.4
    modality = 1.0 if any(term in text for term in ["eeg", "psg", "fmri", "mri", "dti", "electrophysiology"]) else 0.3
    species = 1.0 if any(term in text for term in ["mouse", "mice", "rat", "human", "patient", "rodent"]) else 0.4
    study_type = 1.0 if any(term in text for term in ["meta-analysis", "review", "optogenetic", "cohort", "trial"]) else 0.5
    citation = min(1.0, float(record.citation_count_age_normalized or record.citation_count or 0) / 50.0)
    gap = 1.0 if coverage_gap else 0.2
    open_access = 1.0 if record.is_open_access else 0.0
    return round(0.25 * mechanism + 0.20 * modality + 0.15 * species + 0.15 * study_type + 0.10 * citation + 0.10 * gap + 0.05 * open_access, 3)


def select_anchor_papers(records: list[LiteratureRecord], query_groups: list[str], per_group: int = 5) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for group in query_groups:
        group_terms = set(group.replace("_", " ").split())
        candidates = []
        for record in records:
            text = " ".join([record.title or "", record.abstract or "", " ".join(record.keywords or [])]).lower()
            if any(term in text for term in group_terms) or not group_terms:
                candidates.append(record)
        if not candidates:
            candidates = records
        scored = sorted(candidates, key=lambda item: _score(item, group), reverse=True)[:per_group]
        for rank, record in enumerate(scored, start=1):
            anchors.append(
                {
                    "query_group": group,
                    "rank": rank,
                    "paper_id": record.paper_id,
                    "title": record.title,
                    "year": record.year or record.publication_year or "",
                    "journal": record.journal or "",
                    "anchor_score": _score(record, group),
                    "source": record.source or record.provider or "",
                }
            )
    seen: set[tuple[str, str]] = set()
    unique = []
    for item in anchors:
        key = (item["query_group"], item["paper_id"])
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def write_anchor_papers(path: str | Path, anchors: list[dict[str, Any]]) -> None:
    write_csv(Path(path), anchors)

