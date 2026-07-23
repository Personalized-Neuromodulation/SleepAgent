from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import ensure_parent


def data_asset_registry_path(config: dict[str, Any]) -> Path:
    return _foundation_output_path(config, "data_asset_registry", "data_asset_registry.jsonl")


def update_history_path(config: dict[str, Any]) -> Path:
    return _foundation_output_path(config, "update_history", "foundation_update_history.jsonl")


def write_foundation_data_asset_update(
    config: dict[str, Any],
    *,
    foundation_summary: dict[str, Any],
) -> dict[str, Any]:
    update_cfg = config.get("data_assets", {})
    raw_tables = update_cfg.get("feature_tables", [])
    records = _asset_records(raw_tables, update_cfg)
    if not records:
        return {
            "asset_count": 0,
            "data_asset_registry": str(data_asset_registry_path(config)),
            "update_history": str(update_history_path(config)),
        }

    registry = data_asset_registry_path(config)
    history = update_history_path(config)
    existing_asset_ids = _existing_asset_ids(registry)
    new_records = [record for record in records if record["asset_id"] not in existing_asset_ids]
    if new_records:
        _append_jsonl(registry, new_records)

    created_at = _utc_now()
    event = {
        "event_id": _stable_id("foundation_update", [record["asset_id"] for record in records], update_cfg.get("iteration_id", ""), created_at),
        "created_at": created_at,
        "source": str(update_cfg.get("source", "unknown")),
        "iteration_id": str(update_cfg.get("iteration_id", "")),
        "asset_count": len(records),
        "asset_ids": [record["asset_id"] for record in records],
        "foundation_manifest": str(foundation_summary.get("manifest", "")),
        "foundation_outputs": foundation_summary.get("outputs", {}),
        "experiment_summary": update_cfg.get("experiment_summary", {}),
    }
    _append_jsonl(history, [event])
    return {
        "asset_count": len(records),
        "new_asset_count": len(new_records),
        "data_asset_registry": str(registry),
        "update_history": str(history),
        "asset_ids": event["asset_ids"],
        "update_event_id": event["event_id"],
    }


def data_asset_manifest(config: dict[str, Any], asset_update: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = data_asset_registry_path(config)
    history = update_history_path(config)
    registry_records = _count_jsonl(registry)
    history_records = _count_jsonl(history)
    return {
        "registry": str(registry),
        "update_history": str(history),
        "asset_count": registry_records,
        "update_event_count": history_records,
        "last_update": asset_update or {},
    }


def _asset_records(raw_tables: Any, update_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw_tables, list):
        return []
    records: list[dict[str, Any]] = []
    for item in raw_tables:
        if not isinstance(item, dict):
            continue
        path_value = item.get("path", "")
        if not path_value:
            continue
        path = resolve_path(path_value)
        if not path.exists() or not path.is_file() or path.stat().st_size == 0:
            continue
        profile = _profile_for_table(item)
        file_hash = _sha256(path)
        columns, row_count = _csv_shape(path)
        modality = str(item.get("modality", "")).strip()
        records.append(
            {
                "asset_id": _stable_id("feature_table", modality, file_hash),
                "created_at": _utc_now(),
                "source": str(update_cfg.get("source", "unknown")),
                "iteration_id": str(update_cfg.get("iteration_id", "")),
                "modality": modality,
                "asset_type": "feature_table",
                "path": str(path),
                "profile_path": str(profile) if profile else "",
                "row_count": row_count,
                "column_count": len(columns),
                "feature_count": len([column for column in columns if column not in {"subject_id", "group"}]),
                "columns": columns,
                "sha256": file_hash,
                "size_bytes": path.stat().st_size,
                "experiment_summary": update_cfg.get("experiment_summary", {}),
            }
        )
    return records


def _profile_for_table(item: dict[str, Any]) -> Path | None:
    for key in ("profile_path", "profile", "feature_profile"):
        if item.get(key):
            return resolve_path(item[key])
    return None


def _csv_shape(path: Path) -> tuple[list[str], int]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = list(reader.fieldnames or [])
        return columns, sum(1 for _ in reader)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(*parts: Any) -> str:
    text = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _count_jsonl(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _existing_asset_ids(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    asset_ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("asset_id"):
            asset_ids.add(str(payload["asset_id"]))
    return asset_ids


def _foundation_output_path(config: dict[str, Any], key: str, default_name: str) -> Path:
    value = config.get("outputs", {}).get(key)
    if value:
        return resolve_path(value)
    foundation_dir = config.get("paths", {}).get("foundation_dir", "data/foundation")
    return resolve_path(foundation_dir) / default_name


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
