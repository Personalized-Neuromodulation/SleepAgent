from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.api.normalizer import doi_key, normalize_title
from sleep_ai_scientist.common.io import ensure_parent, write_csv
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def _record_key(record: LiteratureRecord) -> tuple[str, str]:
    doi = doi_key(record.doi)
    if doi:
        return "doi", doi
    pmid = str(record.pmid or "").strip()
    if pmid:
        return "pmid", pmid
    title = normalize_title(record.title)
    return ("title", title) if title else ("paper_id", record.paper_id)


def merge_literature_registry(
    seed_records: list[LiteratureRecord],
    api_records: list[LiteratureRecord],
) -> tuple[list[LiteratureRecord], list[dict[str, Any]]]:
    """Merge seed and API literature with seed metadata taking priority."""
    merged: dict[tuple[str, str], LiteratureRecord] = {}
    duplicate_groups: dict[tuple[str, str], list[LiteratureRecord]] = {}
    seed_ids = {record.paper_id for record in seed_records}

    for record in seed_records + api_records:
        key = _record_key(record)
        if key not in merged:
            merged[key] = record
            duplicate_groups[key] = [record]
            continue
        current = merged[key]
        duplicate_groups[key].append(record)
        current.source = ";".join(sorted(set(filter(None, [current.source, record.source]))))
        current.keywords = sorted(set(current.keywords + record.keywords))
        if current.paper_id not in seed_ids:
            current.abstract = current.abstract or record.abstract
            current.title = current.title or record.title
            current.year = current.year or record.year
            current.doi = current.doi or record.doi
            current.pmid = current.pmid or record.pmid
            current.url = current.url or record.url
            current.notes = ";".join(sorted(set(filter(None, [current.notes, record.notes]))))

    reports = []
    for index, (key, records) in enumerate(duplicate_groups.items(), start=1):
        if len(records) < 2:
            continue
        reports.append(
            {
                "duplicate_group_id": f"dup_{index:04d}",
                "match_type": key[0],
                "match_key": key[1],
                "kept_paper_id": merged[key].paper_id,
                "merged_paper_ids": ";".join(record.paper_id for record in records),
                "sources": ";".join(sorted({record.source for record in records if record.source})),
                "seed_priority_used": any(record.paper_id in seed_ids for record in records),
            }
        )
    return list(merged.values()), reports


def literature_row(record: LiteratureRecord) -> dict[str, Any]:
    payload = record.model_dump(mode="json")
    payload["keywords"] = ";".join(payload.get("keywords") or [])
    return payload


def write_literature_registry(
    records: list[LiteratureRecord],
    csv_path: Path,
    jsonl_path: Path,
    dedup_report_path: Path,
    duplicate_reports: list[dict[str, Any]],
) -> None:
    write_csv(csv_path, [literature_row(record) for record in records])
    ensure_parent(jsonl_path)
    with jsonl_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
    write_csv(dedup_report_path, duplicate_reports)
