from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from sleep_ai_scientist.feature_extraction.schemas import FeatureTable


class MultimodalMerger:
    """Inner-joins extracted modality tables while preserving session rows."""

    def run(self, tables: list[FeatureTable], output_path: str | Path) -> str:
        frames: list[pd.DataFrame] = []
        for table in tables:
            frame = pd.read_csv(table.path)
            if "subject_id" in frame.columns:
                frames.append(_prepare_for_merge(frame, table.modality))
        if not frames:
            merged = pd.DataFrame(columns=["subject_id"])
        else:
            merged = frames[0]
            for frame in frames[1:]:
                keys = ["subject", "subject_id"] if _is_session_level(merged) and _is_session_level(frame) else ["subject"]
                merged = merged.merge(frame, on=keys, how="inner")
                if "subject_id_x" in merged.columns and "subject_id_y" in merged.columns:
                    merged["subject_id"] = merged["subject_id_x"].where(merged["subject_id_x"].astype(str).ne(merged["subject"]), merged["subject_id_y"])
                    merged = merged.drop(columns=["subject_id_x", "subject_id_y"])
            if "subject_id" not in merged.columns:
                merged.insert(0, "subject_id", merged["subject"])
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(output_path, index=False)
        return str(output_path)


def _prepare_for_merge(frame: pd.DataFrame, modality: str) -> pd.DataFrame:
    prepared = frame.copy()
    if "subject" in prepared.columns:
        prepared["subject"] = prepared["subject"].map(_base_subject)
    else:
        prepared.insert(1, "subject", prepared["subject_id"].map(_base_subject))

    rename: dict[str, str] = {}
    modality_prefix = _prefix(modality)
    for column in prepared.columns:
        if column in {"subject", "subject_id"}:
            continue
        if not str(column).startswith(f"{modality_prefix}_"):
            rename[column] = f"{modality_prefix}_{column}"
    return prepared.rename(columns=rename)


def _is_session_level(frame: pd.DataFrame) -> bool:
    if "subject_id" not in frame.columns or "subject" not in frame.columns:
        return False
    return bool(frame["subject_id"].astype(str).ne(frame["subject"].astype(str)).any())


def _base_subject(value: object) -> str:
    match = re.search(r"(sub-[A-Za-z0-9]+)", str(value))
    return match.group(1) if match else str(value)


def _prefix(modality: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", modality.lower()).strip("_") or "modality"
