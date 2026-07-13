from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.feature_extraction.agents import (
    EEGFeatureAgent,
    FMRIFeatureAgent,
    MultimodalMergeAgent,
    QCFeatureAgent,
    ScaleFeatureAgent,
    TabularFeatureAgent,
)
from sleep_ai_scientist.feature_extraction.profile_builder import ProfileBuilder
from sleep_ai_scientist.feature_extraction.schemas import FeatureExtractionResult, FeatureTable
from sleep_ai_scientist.schemas.experiment import ExperimentPlan


def run_feature_extraction(config: dict[str, Any], plan: ExperimentPlan) -> FeatureExtractionResult:
    output_root = Path(config.get("output_root", "outputs/features"))
    output_dir = output_root / plan.plan_id
    output_dir.mkdir(parents=True, exist_ok=True)

    tables: list[FeatureTable] = []
    modalities = _selected_modalities(config)
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
    for modality in sorted(modalities - {"fmri", "eeg", "scale", "scales"}):
        modality_config = config.get(modality, {})
        table = TabularFeatureAgent(modality, modality_config).run(plan_id=plan.plan_id, output_dir=output_dir)
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


def _selected_modalities(config: dict[str, Any]) -> set[str]:
    raw = config.get("modalities", "auto")
    if isinstance(raw, str):
        explicit = {raw.lower()}
    else:
        explicit = {str(item).lower() for item in raw}
    if explicit and explicit != {"auto"}:
        return explicit

    selected: set[str] = set()
    path_keys = ("features_csv", "raw_table", "input_root", "raw_root")
    fmri = config.get("fmri", {})
    if _has_any_path(fmri, ("features_csv", "derivatives_root", "output_root", "input_root", "raw_root", "raw_table")):
        selected.add("fmri")
    if _has_any_path(config.get("eeg", {}), path_keys):
        selected.add("eeg")
    if _has_any_path(config.get("scales", {}), path_keys):
        selected.add("scales")
    for key, value in config.items():
        if key in {"enabled", "output_root", "modalities", "fmri", "eeg", "scales"}:
            continue
        if isinstance(value, dict) and _has_any_path(value, path_keys):
            selected.add(str(key).lower())
    return selected


def _has_any_path(config: dict[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        value = str(config.get(key, "") or "").strip()
        if value:
            return True
    return False
