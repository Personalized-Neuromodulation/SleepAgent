from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.feature_extraction.agents import (
    EEGFeatureAgent,
    FMRIFeatureAgent,
    MultimodalMergeAgent,
    QCFeatureAgent,
    ScaleFeatureAgent,
)
from sleep_ai_scientist.feature_extraction.profile_builder import ProfileBuilder
from sleep_ai_scientist.feature_extraction.schemas import FeatureExtractionResult, FeatureTable
from sleep_ai_scientist.schemas.experiment import ExperimentPlan


def run_feature_extraction(config: dict[str, Any], plan: ExperimentPlan) -> FeatureExtractionResult:
    output_root = Path(config.get("output_root", "outputs/features"))
    output_dir = output_root / plan.plan_id
    output_dir.mkdir(parents=True, exist_ok=True)

    tables: list[FeatureTable] = []
    modalities = {str(item).lower() for item in config.get("modalities", ["fmri", "eeg", "scales"])}
    if "fmri" in modalities:
        table = FMRIFeatureAgent(config.get("fmri", {})).run(plan_id=plan.plan_id, output_dir=output_dir)
        if table:
            tables.append(table)
    if "eeg" in modalities:
        table = EEGFeatureAgent(config.get("eeg", {})).run(plan_id=plan.plan_id, output_dir=output_dir)
        if table:
            tables.append(table)
    if "scales" in modalities or "scale" in modalities:
        table = ScaleFeatureAgent(config.get("scales", {})).run(plan_id=plan.plan_id, output_dir=output_dir)
        if table:
            tables.append(table)

    tables = QCFeatureAgent().run(tables)
    merged_path = MultimodalMergeAgent().run(tables, output_dir / "multimodal_features.csv")
    profile_path = output_dir / "analysis_ready_profile.yaml"
    ProfileBuilder().build(tables, profile_path)
    return FeatureExtractionResult(
        plan_id=plan.plan_id,
        output_dir=str(output_dir),
        tables=tables,
        profile_path=str(profile_path),
        merged_features_path=merged_path,
        metadata={"modalities": sorted({table.modality for table in tables})},
    )
