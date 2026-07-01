from __future__ import annotations

from typing import Any

from sleep_ai_scientist.api.normalizer import doi_key, normalize_title
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def literature_key(record: LiteratureRecord) -> tuple[str, str]:
    doi = doi_key(record.doi)
    if doi:
        return "doi", doi
    pmid = str(record.pmid or "").strip()
    if pmid:
        return "pmid", pmid
    pmcid = str(getattr(record, "pmcid", "") or "").strip()
    if pmcid:
        return "pmcid", pmcid
    title = normalize_title(record.title)
    return ("title", title) if title else ("paper_id", record.paper_id)


def deduplicate_records(records: list[LiteratureRecord], seed_ids: set[str] | None = None) -> tuple[list[LiteratureRecord], list[dict[str, Any]]]:
    seed_ids = seed_ids or set()
    merged: dict[tuple[str, str], LiteratureRecord] = {}
    groups: dict[tuple[str, str], list[LiteratureRecord]] = {}
    for record in records:
        key = literature_key(record)
        groups.setdefault(key, []).append(record)
        if key not in merged:
            merged[key] = record
            continue
        current = merged[key]
        if record.paper_id in seed_ids and current.paper_id not in seed_ids:
            merged[key] = record
            record.source = ";".join(sorted(set(filter(None, [record.source, current.source]))))
            record.keywords = sorted(set(record.keywords + current.keywords))
            continue
        current.source = ";".join(sorted(set(filter(None, [current.source, record.source]))))
        current.keywords = sorted(set(current.keywords + record.keywords))
        current.abstract = current.abstract or record.abstract
        current.year = current.year or record.year
        current.journal = current.journal or record.journal
    report = []
    for idx, (key, values) in enumerate(groups.items(), start=1):
        if len(values) < 2:
            continue
        report.append(
            {
                "duplicate_group_id": f"lit_dup_{idx:05d}",
                "match_type": key[0],
                "match_key": key[1],
                "kept_paper_id": merged[key].paper_id,
                "merged_paper_ids": ";".join(item.paper_id for item in values),
                "seed_priority_used": any(item.paper_id in seed_ids for item in values),
            }
        )
    return list(merged.values()), report

