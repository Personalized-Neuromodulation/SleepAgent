from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.feature_extraction.extractors import (
    EEGFeatureExtractor,
    FMRIFeatureExtractor,
    MultimodalMerger,
    QCProcessor,
    ScaleFeatureExtractor,
    TabularFeatureExtractor,
)
from sleep_ai_scientist.feature_extraction.profile_builder import ProfileBuilder
from sleep_ai_scientist.feature_extraction.schemas import FeatureExtractionResult, FeatureTable
from sleep_ai_scientist.schemas.experiment import ExperimentPlan


def run_feature_extraction(config: dict[str, Any], plan: ExperimentPlan) -> FeatureExtractionResult:
    output_root = Path(config.get("output_root", "outputs/features"))
    output_root.mkdir(parents=True, exist_ok=True)
    _ensure_feature_root_dirs(output_root, config)

    tables: list[FeatureTable] = []
    modalities = _selected_modalities(config)
    if "fmri" in modalities:
        table = FMRIFeatureExtractor(config.get("fmri", {})).run(
            plan_id=plan.plan_id,
            output_dir=_modality_output_dir(output_root, "fmri", plan.plan_id),
        )
        if table:
            tables.append(table)
    if "eeg" in modalities:
        table = EEGFeatureExtractor(config.get("eeg", {})).run(
            plan_id=plan.plan_id,
            output_dir=_modality_output_dir(output_root, "eeg", plan.plan_id),
        )
        if table:
            tables.append(table)
    if "scales" in modalities or "scale" in modalities:
        table = ScaleFeatureExtractor(config.get("scales", {})).run(
            plan_id=plan.plan_id,
            output_dir=_modality_output_dir(output_root, "scales", plan.plan_id),
        )
        if table:
            tables.append(table)
    for modality in sorted(modalities - {"fmri", "eeg", "scale", "scales"}):
        modality_config = config.get(modality, {})
        table = TabularFeatureExtractor(modality, modality_config).run(
            plan_id=plan.plan_id,
            output_dir=_modality_output_dir(output_root, modality, plan.plan_id),
        )
        if table:
            tables.append(table)

    tables = QCProcessor().run(tables)
    merged_path = MultimodalMerger().run(tables, output_root / "multimodal" / plan.plan_id / "multimodal_features.csv")
    profile_path = output_root / "profile" / plan.plan_id / "analysis_ready_profile.yaml"
    ProfileBuilder().build(tables, profile_path)
    return FeatureExtractionResult(
        plan_id=plan.plan_id,
        output_dir=str(output_root),
        tables=tables,
        profile_path=str(profile_path),
        merged_features_path=merged_path,
        metadata={"modalities": sorted({table.modality for table in tables})},
    )


def _modality_output_dir(output_root: Path, modality: str, plan_id: str) -> Path:
    return output_root / _modality_folder(modality) / plan_id


def _ensure_feature_root_dirs(output_root: Path, config: dict[str, Any]) -> None:
    for modality in sorted(_declared_modalities(config)):
        (output_root / _modality_folder(modality)).mkdir(parents=True, exist_ok=True)
    (output_root / "multimodal").mkdir(parents=True, exist_ok=True)
    (output_root / "profile").mkdir(parents=True, exist_ok=True)


def _declared_modalities(config: dict[str, Any]) -> set[str]:
    declared = {"fmri", "eeg", "scales", "dti", "mri"}
    raw = config.get("modalities", "auto")
    if isinstance(raw, str):
        if raw.lower() != "auto":
            declared.add(raw.lower())
    else:
        declared.update(str(item).lower() for item in raw)
    for key, value in config.items():
        if key in {"enabled", "output_root", "modalities"}:
            continue
        if isinstance(value, dict):
            declared.add(str(key).lower())
    return {_modality_folder(item) for item in declared if str(item).strip()}


def _modality_folder(modality: str) -> str:
    lowered = str(modality).strip().lower()
    if lowered in {"scale", "scales"}:
        return "scales"
    return lowered


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
