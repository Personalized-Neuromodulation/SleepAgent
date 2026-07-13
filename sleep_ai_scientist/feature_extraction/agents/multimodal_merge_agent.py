from __future__ import annotations

from pathlib import Path

import pandas as pd

from sleep_ai_scientist.feature_extraction.schemas import FeatureTable


class MultimodalMergeAgent:
    """Inner-joins extracted modality tables on subject_id."""

    def run(self, tables: list[FeatureTable], output_path: str | Path) -> str:
        frames: list[pd.DataFrame] = []
        for table in tables:
            frame = pd.read_csv(table.path)
            if "subject_id" in frame.columns:
                frames.append(frame)
        if not frames:
            merged = pd.DataFrame(columns=["subject_id"])
        else:
            merged = frames[0]
            for frame in frames[1:]:
                merged = merged.merge(frame, on="subject_id", how="inner")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(output_path, index=False)
        return str(output_path)
