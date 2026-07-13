from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.feature_extraction.agents.tabular_utils import extract_tabular_features
from sleep_ai_scientist.feature_extraction.schemas import FeatureTable


class TabularFeatureAgent:
    """Extracts a feature table for modalities represented by tabular files."""

    def __init__(self, modality: str, config: dict[str, Any] | None = None) -> None:
        self.modality = modality
        self.config = config or {}

    def run(self, *, plan_id: str, output_dir: str | Path) -> FeatureTable | None:
        frame, source = extract_tabular_features(self.config, modality=self.modality)
        if frame is None:
            return None
        output_dir = Path(output_dir)
        if "subject_id" not in frame.columns:
            frame.insert(0, "subject_id", [f"row_{idx}" for idx in range(len(frame))])
        target = output_dir / f"{self.modality.lower()}_features.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(target, index=False)
        return FeatureTable(
            modality=_display_modality(self.modality),
            path=str(target),
            feature_columns=[column for column in frame.columns if column not in {"subject_id", "subject"}],
            metadata={"source": str(source), "plan_id": plan_id},
        )


def _display_modality(value: str) -> str:
    lowered = value.lower()
    if lowered in {"dti", "mri"}:
        return lowered.upper()
    return value
