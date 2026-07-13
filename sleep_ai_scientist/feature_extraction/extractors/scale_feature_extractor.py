from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.feature_extraction.extractors.tabular_utils import extract_tabular_features
from sleep_ai_scientist.feature_extraction.schemas import FeatureTable


class ScaleFeatureExtractor:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def run(self, *, plan_id: str, output_dir: str | Path) -> FeatureTable | None:
        frame, source = extract_tabular_features(self.config, modality="scales")
        if frame is None:
            return None
        output_dir = Path(output_dir)
        if "subject_id" not in frame.columns:
            frame.insert(0, "subject_id", [f"row_{idx}" for idx in range(len(frame))])
        target = output_dir / "scale_features.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(target, index=False)
        return FeatureTable(
            modality="scales",
            path=str(target),
            feature_columns=[c for c in frame.columns if c not in {"subject_id", "subject"}],
            metadata={"source": str(source), "plan_id": plan_id, "extraction": "questionnaire_table_summary"},
        )
