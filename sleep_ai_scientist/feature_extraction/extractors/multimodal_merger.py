from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from sleep_ai_scientist.feature_extraction.schemas import FeatureTable


class MultimodalMerger:
    """Inner-joins extracted modality tables on the normalized subject key."""

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
                merged = merged.merge(frame, on="subject", how="inner")
            if "subject_id" not in merged.columns:
                merged.insert(0, "subject_id", merged["subject"])
            else:
                merged["subject_id"] = merged["subject"]
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
    prepared = prepared.rename(columns=rename)

    subject_ids = prepared[["subject", "subject_id"]].copy()
    features = prepared.drop(columns=["subject_id"])
    if features["subject"].duplicated().any():
        numeric_cols = [column for column in features.columns if column != "subject" and pd.api.types.is_numeric_dtype(features[column])]
        features = features.groupby("subject", as_index=False)[numeric_cols].mean()
        subject_ids = subject_ids.groupby("subject", as_index=False).first()
        features = subject_ids.merge(features, on="subject", how="left").drop(columns=["subject_id"])
    return features


def _base_subject(value: object) -> str:
    match = re.search(r"(sub-[A-Za-z0-9]+)", str(value))
    return match.group(1) if match else str(value)


def _prefix(modality: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", modality.lower()).strip("_") or "modality"
