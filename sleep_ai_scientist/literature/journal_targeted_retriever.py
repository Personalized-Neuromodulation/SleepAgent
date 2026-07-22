from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import config_path, resolve_path
from sleep_ai_scientist.common.io import write_csv
from sleep_ai_scientist.grounding.literature_loader import load_literature
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def retrieve_journal_targeted_records(config: dict[str, Any]) -> list[LiteratureRecord]:
    """Load prepared journal-targeted retrieval records.

    The network-facing targeted retrieval fan-out is intentionally not executed
    from default tests. This function accepts precomputed channel output when a
    config points at one, then routes those records through identity resolution.
    """
    targeted = config.get("journal_targeted", {})
    input_path = targeted.get("records_path") or targeted.get("input_records")
    if not input_path:
        return []
    path = resolve_path(input_path, Path(config["_project_root"]))
    if not path.exists() or path.stat().st_size == 0:
        return []
    records = load_literature(path)
    for record in records:
        record.retrieval_channel = "journal_targeted"
    return records


def write_journal_targeted_outputs(config: dict[str, Any], records: list[LiteratureRecord]) -> dict[str, str]:
    csv_path = config_path(config, "journal_targeted_records_csv", "data/literature/journal_targeted_records.csv")
    jsonl_path = config_path(config, "journal_targeted_records_jsonl", "data/literature/journal_targeted_records.jsonl")
    rows = [record.model_dump(mode="json") for record in records]
    write_csv(csv_path, rows)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"csv": str(csv_path), "jsonl": str(jsonl_path)}
