from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sleep_ai_scientist.feature_extraction.schemas import FeatureTable


class ScaleFeatureAgent:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def run(self, *, plan_id: str, output_dir: str | Path) -> FeatureTable | None:
        source = self._find_source()
        if source is None:
            return None
        output_dir = Path(output_dir)
        frame = pd.read_csv(source)
        if "subject_id" not in frame.columns:
            frame.insert(0, "subject_id", [f"row_{idx}" for idx in range(len(frame))])
        target = output_dir / "scale_features.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(target, index=False)
        return FeatureTable(modality="scales", path=str(target), feature_columns=[c for c in frame.columns if c != "subject_id"], metadata={"source": str(source), "plan_id": plan_id})

    def _find_source(self) -> Path | None:
        explicit = self.config.get("features_csv")
        if explicit and Path(explicit).exists():
            return Path(explicit)
        fixture = Path("data/fixtures/toy_scale_features.csv")
        return fixture if fixture.exists() else None
