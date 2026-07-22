from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.knowledge_sources.base import make_id


def build_tool_method_records(config: dict[str, Any], source_path: str | Path = "configs/tools_methods_registry.yaml") -> list[dict[str, Any]]:
    payload = read_yaml(resolve_path(source_path, Path(config["_project_root"])))
    records = []
    for name, data in payload.get("tools", {}).items():
        records.append(
            {
                "tool_id": make_id("tool", name),
                "name": name,
                "category": data.get("category", ""),
                "modality": data.get("modality", ""),
                "role_json": data.get("role", []),
                "source_url": data.get("source_url", ""),
                "version": str(data.get("version", "")),
                "notes": data.get("notes", "Curated method/tool registry entry."),
            }
        )
    for name, data in payload.get("methods", {}).items():
        records.append(
            {
                "tool_id": make_id("method", name),
                "name": name,
                "category": "method",
                "modality": data.get("modality", ""),
                "role_json": data.get("role", []),
                "source_url": data.get("source_url", ""),
                "version": "",
                "notes": data.get("notes", "Curated method registry entry."),
            }
        )
    return records

