from __future__ import annotations

from typing import Any

from sleep_ai_scientist.literature.identity_resolution import normalize_doi, normalize_pmcid, normalize_pmid, normalize_title
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def literature_key(record: LiteratureRecord) -> tuple[str, str]:
    doi = normalize_doi(record.doi)
    if doi:
        return "doi", doi
    pmid = normalize_pmid(record.pmid)
    if pmid:
        return "pmid", pmid
    pmcid = normalize_pmcid(getattr(record, "pmcid", "") or "")
    if pmcid:
        return "pmcid", pmcid
    title = normalize_title(record.title)
    return ("title", title) if title else ("paper_id", record.paper_id)


def deduplicate_records(records: list[LiteratureRecord]) -> tuple[list[LiteratureRecord], list[dict[str, Any]]]:
    merged: dict[tuple[str, str], LiteratureRecord] = {}
    groups: dict[tuple[str, str], list[LiteratureRecord]] = {}
    for record in records:
        key = literature_key(record)
        groups.setdefault(key, []).append(record)
        if key not in merged:
            merged[key] = record
            continue
        current = merged[key]
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
            }
        )
    return list(merged.values()), report
