from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.feature_extraction.extractors.tabular_utils import extract_tabular_features
from sleep_ai_scientist.feature_extraction.extractors.scale_workbook import (
    extract_scale_workbooks,
    select_baseline_scale_rows,
)
from sleep_ai_scientist.feature_extraction.schemas import FeatureTable


class ScaleFeatureExtractor:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def run(self, *, plan_id: str, output_dir: str | Path) -> FeatureTable | None:
        xlsx_root = self._xlsx_root()
        if xlsx_root is not None:
            return self._run_xlsx(xlsx_root, plan_id=plan_id, output_dir=output_dir)

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

    def _xlsx_root(self) -> Path | None:
        root_value = self.config.get("input_root") or self.config.get("raw_root")
        if not root_value:
            return None
        root = Path(root_value)
        if not root.exists() or not any(root.rglob("*_scales.xlsx")):
            return None
        return root

    def _run_xlsx(self, root: Path, *, plan_id: str, output_dir: str | Path) -> FeatureTable | None:
        long_frame, workbook_audit = extract_scale_workbooks(root)
        if long_frame.empty:
            return None
        baseline, baseline_audit = select_baseline_scale_rows(long_frame)
        if baseline.empty:
            return None

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        long_path = output / "scale_features_long.csv"
        baseline_path = output / "scale_features.csv"
        long_frame.to_csv(long_path, index=False)
        baseline.to_csv(baseline_path, index=False)
        return FeatureTable(
            modality="scales",
            path=str(baseline_path),
            feature_columns=[column for column in baseline.columns if column not in {"subject_id", "subject"}],
            metadata={
                "source": str(root),
                "plan_id": plan_id,
                "extraction": "visit_structured_questionnaire_xlsx",
                "long_table": str(long_path),
                "workbook_audit": workbook_audit,
                "baseline_audit": baseline_audit,
            },
        )
