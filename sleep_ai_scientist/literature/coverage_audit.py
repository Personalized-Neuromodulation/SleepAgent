from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_csv, write_json
from sleep_ai_scientist.schemas.literature import LiteratureRecord

ANIMAL_TERMS = {"mouse", "mice", "rat", "rodent", "animal", "optogenetic", "chemogenetic", "dreadd"}
HUMAN_TERMS = {"human", "patient", "participants", "insomnia", "polysomnography", "psg"}
CELLULAR_TERMS = {"adenosine", "gaba", "orexin", "cytokine", "interleukin", "tnf", "melatonin", "histamine"}
GROUP_STOP_TERMS = {"sleep", "human", "animal"}


def _text(record: LiteratureRecord) -> str:
    return " ".join([record.title or "", record.abstract or "", " ".join(record.keywords or []), record.notes or ""]).lower()


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def build_coverage_audit(records: list[LiteratureRecord], query_groups: list[str], duplicate_groups: int = 0) -> dict[str, Any]:
    records_by_group: Counter[str] = Counter()
    records_by_provider: Counter[str] = Counter()
    for record in records:
        text = _text(record)
        for group in query_groups:
            group_tokens = set(group.replace("_", " ").split()) - GROUP_STOP_TERMS
            if group_tokens and any(token in text for token in group_tokens):
                records_by_group[group] += 1
        source = record.provider or record.source or "unknown"
        for provider in str(source).replace("api:", "").split(","):
            records_by_provider[provider.strip() or "unknown"] += 1
    empty_groups = [group for group in query_groups if records_by_group.get(group, 0) == 0]
    sparse_groups = [group for group in query_groups if 0 < records_by_group.get(group, 0) < 10]
    citation_available = sum(1 for record in records if record.citation_count is not None)
    journal_available = sum(1 for record in records if record.journal)
    total = len(records)
    return {
        "record_count": total,
        "records_by_query_group": dict(records_by_group),
        "records_by_provider": dict(records_by_provider),
        "human_count": sum(1 for record in records if _contains_any(_text(record), HUMAN_TERMS)),
        "animal_count": sum(1 for record in records if _contains_any(_text(record), ANIMAL_TERMS)),
        "cellular_molecular_count": sum(1 for record in records if _contains_any(_text(record), CELLULAR_TERMS)),
        "open_access_count": sum(1 for record in records if record.is_open_access),
        "citation_availability_rate": round(citation_available / total, 3) if total else 0.0,
        "journal_availability_rate": round(journal_available / total, 3) if total else 0.0,
        "duplicate_rate": round(duplicate_groups / max(1, total + duplicate_groups), 3),
        "sparse_query_groups": sparse_groups,
        "empty_query_groups": empty_groups,
        "recommended_next_query_groups": empty_groups[:10] or sparse_groups[:10],
    }


def write_coverage_audit(audit: dict[str, Any], output_csv: str | Path, output_json: str | Path) -> None:
    rows = [
        {"query_group": group, "record_count": count, "status": "empty" if count == 0 else "sparse" if count < 10 else "covered"}
        for group, count in sorted(audit.get("records_by_query_group", {}).items())
    ]
    for group in audit.get("empty_query_groups", []):
        if group not in audit.get("records_by_query_group", {}):
            rows.append({"query_group": group, "record_count": 0, "status": "empty"})
    write_csv(Path(output_csv), rows)
    write_json(Path(output_json), audit)
