from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.knowledge_sources.base import make_id, now_dt


def build_guideline_records(config: dict[str, Any], source_path: str | Path = "configs/guideline_sources.yaml") -> list[dict[str, Any]]:
    payload = read_yaml(resolve_path(source_path, Path(config["_project_root"])))
    aasm = payload.get("guideline_sources", {}).get("aasm", {})
    topics = aasm.get("topics", [])
    records = []
    for topic in topics:
        title = f"AASM guideline metadata: {topic}"
        records.append(
            {
                "guideline_id": make_id("guideline", aasm.get("organization", "AASM"), topic),
                "title": title,
                "organization": aasm.get("organization", "American Academy of Sleep Medicine"),
                "year": None,
                "topic": topic,
                "population": "",
                "condition": topic,
                "intervention": "",
                "recommendation_summary": "Metadata-only curated guideline entry; consult official source for full recommendations.",
                "recommendations_json": [],
                "recommendation_strength": "",
                "evidence_certainty": "",
                "methodology": "curated metadata plus public citation discovery path",
                "source_url": "https://aasm.org/clinical-resources/practice-standards/",
                "doi": "",
                "pmid": "",
                "access_status": "metadata_only",
                "retrieved_at": now_dt(),
                "notes": "No restricted guideline full text copied.",
            }
        )
    return records
