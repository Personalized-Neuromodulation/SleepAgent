from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.knowledge_sources.base import make_id


def build_diagnostic_terms(config: dict[str, Any], source_path: str | Path = "configs/diagnostic_taxonomy.yaml") -> list[dict[str, Any]]:
    payload = read_yaml(resolve_path(source_path, Path(config["_project_root"])))
    version = payload.get("taxonomy", {}).get("version", "")
    records = []
    for category, data in payload.get("sleep_disorder_categories", {}).items():
        records.append(
            {
                "term_id": make_id("diagnostic", version, category),
                "source": "SleepAgent curated taxonomy; ICSD/MeSH metadata only",
                "term": category.replace("_", " "),
                "category": category,
                "parent_term": "sleep disorders",
                "synonyms_json": data.get("synonyms", []),
                "definition": "",
                "version": version,
                "downstream_relevance_json": data.get("downstream_relevance", []),
                "notes": "No restricted ICSD text copied.",
            }
        )
    return records

