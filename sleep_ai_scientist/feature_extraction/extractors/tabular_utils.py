from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


def extract_tabular_features(
    config: dict[str, Any],
    *,
    modality: str,
    preferred_patterns: tuple[str, ...] = ("*.csv", "*.tsv", "*.json"),
) -> tuple[pd.DataFrame | None, str]:
    source = _first_existing(config, ("features_csv", "raw_table"))
    if source:
        return _read_feature_like_table(source), str(source)

    root = config.get("input_root") or config.get("raw_root")
    if not root:
        return None, ""
    root_path = Path(root)
    if not root_path.exists():
        return None, ""

    rows: list[dict[str, Any]] = []
    for pattern in preferred_patterns:
        for path in sorted(root_path.rglob(pattern)):
            if path.name.startswith("."):
                continue
            frame = _read_table(path)
            if frame is None or frame.empty:
                continue
            rows.extend(_table_to_subject_rows(frame, path, modality=modality))
    if not rows:
        return None, ""
    return pd.DataFrame(rows), str(root_path)


def normalize_feature_table(frame: pd.DataFrame, *, source_path: Path | None = None, modality: str = "") -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.copy()
    subject_col = _find_subject_column(frame)
    if subject_col and subject_col != "subject_id":
        frame = frame.rename(columns={subject_col: "subject_id"})
    if "subject_id" not in frame.columns:
        subject = _subject_from_path(source_path) if source_path else ""
        if subject:
            frame.insert(0, "subject_id", subject)
        else:
            frame.insert(0, "subject_id", [f"row_{idx}" for idx in range(len(frame))])
    frame["subject_id"] = frame["subject_id"].astype(str)
    if "subject" not in frame.columns:
        frame.insert(1, "subject", frame["subject_id"].map(_base_subject_id))
    numeric_cols = [column for column in frame.columns if column != "subject_id" and pd.api.types.is_numeric_dtype(frame[column])]
    passthrough = ["subject_id"]
    if "subject" in frame.columns:
        passthrough.append("subject")
    passthrough.extend(numeric_cols)
    cleaned = frame[passthrough].copy()
    for column in numeric_cols:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
    if cleaned["subject_id"].duplicated().any():
        aggregations = {column: "mean" for column in numeric_cols}
        if "subject" in cleaned.columns:
            aggregations["subject"] = "first"
        cleaned = cleaned.groupby("subject_id", as_index=False).agg(aggregations)
    return cleaned


def _read_feature_like_table(path: Path) -> pd.DataFrame:
    frame = _read_table(path)
    if frame is None:
        return pd.DataFrame()
    return normalize_feature_table(frame, source_path=path)


def _read_table(path: Path) -> pd.DataFrame | None:
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(path)
        if suffix == ".tsv":
            return pd.read_csv(path, sep="\t")
        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return pd.DataFrame(payload)
            if isinstance(payload, dict):
                return pd.DataFrame([payload])
    except Exception:
        return None
    return None


def _table_to_subject_rows(frame: pd.DataFrame, path: Path, *, modality: str) -> list[dict[str, Any]]:
    normalized = normalize_feature_table(frame, source_path=path, modality=modality)
    if normalized.empty:
        return []
    if "subject_id" in normalized.columns and len(normalized) == 1:
        return [dict(normalized.iloc[0])]
    if "subject_id" in normalized.columns and not normalized["subject_id"].astype(str).str.startswith("row_").all():
        return [dict(row) for _, row in normalized.iterrows()]

    numeric = normalized.select_dtypes(include=["number"])
    if numeric.empty:
        return []
    subject = _subject_from_path(path) or path.stem
    row: dict[str, Any] = {"subject_id": subject}
    for column in numeric.columns:
        values = pd.to_numeric(numeric[column], errors="coerce")
        row[f"{_clean_name(column)}_mean"] = float(values.mean()) if values.notna().any() else None
        row[f"{_clean_name(column)}_std"] = float(values.std()) if values.notna().sum() > 1 else 0.0
    return [row]


def _first_existing(config: dict[str, Any], keys: tuple[str, ...]) -> Path | None:
    for key in keys:
        value = str(config.get(key, "") or "").strip()
        if value and Path(value).exists():
            return Path(value)
    return None


def _find_subject_column(frame: pd.DataFrame) -> str | None:
    aliases = {"subject_id", "subject", "sub", "participant_id", "participant", "被试", "被试编号"}
    for column in frame.columns:
        if str(column).strip().lower() in aliases:
            return column
    return None


def _subject_from_path(path: Path | None) -> str:
    if path is None:
        return ""
    for part in reversed(path.parts):
        match = re.search(r"(sub-[A-Za-z0-9]+)", part)
        if match:
            return match.group(1)
    return ""


def _base_subject_id(value: Any) -> str:
    match = re.search(r"(sub-[A-Za-z0-9]+)", str(value))
    return match.group(1) if match else str(value)


def _clean_name(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(value).strip()).strip("_")
