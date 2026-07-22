from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.knowledge_sources.base import make_id


def build_standard_records(config: dict[str, Any], source_path: str | Path = "configs/sleep_standard_sources.yaml") -> list[dict[str, Any]]:
    payload = read_yaml(resolve_path(source_path, Path(config["_project_root"])))
    manual = payload.get("standards", {}).get("aasm_scoring_manual", {})
    categories = payload.get("standards", {}).get("scoring_rule_categories", [])
    records = []
    for category in categories:
        records.append(
            {
                "standard_id": make_id("standard", manual.get("title"), manual.get("version"), category),
                "title": manual.get("title", "AASM Manual for the Scoring of Sleep and Associated Events"),
                "organization": manual.get("organization", "American Academy of Sleep Medicine"),
                "version": str(manual.get("version", "")),
                "year": manual.get("year"),
                "topic": "sleep scoring",
                "rule_category": category,
                "rule_summary": f"Public metadata-only category for {category}; restricted manual text is not copied.",
                "source_url": manual.get("source_url"),
                "access_status": manual.get("access_status", "restricted/manual_metadata_only"),
                "notes": "Metadata-only. Used for terminology/QC, not hypothesis support evidence.",
            }
        )
    return records

