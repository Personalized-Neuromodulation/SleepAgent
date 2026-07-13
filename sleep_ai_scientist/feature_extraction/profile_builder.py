from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sleep_ai_scientist.common.io import write_yaml
from sleep_ai_scientist.schemas.data_profile import DataProfile, FeatureProfile
from sleep_ai_scientist.schemas.experiment import ExperimentPlan
from sleep_ai_scientist.feature_extraction.schemas import FeatureTable


FMRI_MECHANISM_FEATURES = [
    "thalamus_DMN_FC",
    "thalamus_salience_FC",
    "thalamus_frontoparietal_FC",
    "DMN_FC",
    "salience_FC",
    "frontoparietal_FC",
]
FMRI_QC_COVARIATES = ["mean_FD", "mean_DVARS", "percent_high_motion", "max_FD"]
FMRI_EXPLORATORY_OUTCOMES = ["global_signal_psd_power_mean", "qc_signal_post_DVARS_mean"]


class ProfileBuilder:
    """Builds an analysis-ready profile from extracted feature tables."""

    def build(self, tables: list[FeatureTable], output_path: str | Path) -> DataProfile:
        features: list[FeatureProfile] = []
        for table in tables:
            frame = pd.read_csv(table.path)
            for column in table.feature_columns:
                if column == table.subject_id_column or column not in frame.columns:
                    continue
                series = frame[column]
                role = _infer_role(column)
                features.append(
                    FeatureProfile(
                        feature_name=column,
                        modality=table.modality,
                        source_file=table.path,
                        source_column=column,
                        missing_rate=float(series.isna().mean()) if len(series) else None,
                        n_available=int(series.notna().sum()),
                        qc_status="pass",
                        approved=True,
                        role=role,
                    )
                )
        profile = DataProfile(profile_type="analysis_ready_profile", features=features)
        write_yaml(Path(output_path), profile.model_dump())
        return profile


class TestabilityPrecheck:
    """Adapts a multimodal experiment plan to the modalities actually available."""

    def run(self, plan: ExperimentPlan, profile: DataProfile) -> ExperimentPlan:
        available_modalities = sorted({feature.modality.lower() for feature in profile.features if feature.source_file})
        missing_modalities = sorted(set(_requested_modalities(plan)) - set(available_modalities))
        profile_names = {feature.feature_name for feature in profile.features}
        metadata = dict(plan.metadata)
        metadata["testability_precheck"] = {
            "available_modalities": available_modalities,
            "missing_modalities": missing_modalities,
            "full_hypothesis_testable": not missing_modalities,
        }
        if available_modalities == ["fmri"] and missing_modalities:
            predictors = [name for name in FMRI_MECHANISM_FEATURES if name in profile_names][:4]
            outcomes = [name for name in FMRI_EXPLORATORY_OUTCOMES if name in profile_names]
            if not outcomes:
                outcomes = [name for name in profile_names if name not in predictors and name not in FMRI_QC_COVARIATES][:2]
            covariates = [name for name in FMRI_QC_COVARIATES if name in profile_names]
            plan.predictors = predictors
            plan.outcomes = outcomes
            plan.covariates = covariates
            plan.negative_controls = []
            plan.primary_tests = [
                {
                    "test_id": f"{plan.plan_id}_{predictor}_{outcome}",
                    "predictor": predictor,
                    "outcome": outcome,
                    "question": f"fMRI-only submechanism: does {predictor} relate to {outcome}?",
                }
                for predictor in predictors
                for outcome in outcomes
            ]
            metadata["testability_precheck"].update(
                {
                    "mode": "partial_fmri_only",
                    "partial_testable_components": predictors,
                    "unresolved_components": missing_modalities,
                    "reason": "Only fMRI features are available; multimodal hypothesis was converted to fMRI-only submechanism tests.",
                }
            )
        plan.metadata = metadata
        return plan


def _infer_role(column: str) -> str:
    lowered = column.lower()
    if lowered in {"isi", "psqi"} or "score" in lowered or "symptom" in lowered:
        return "outcome"
    if lowered in {item.lower() for item in FMRI_QC_COVARIATES} or lowered in {"age", "sex", "medication"}:
        return "covariate"
    return "feature"


def _requested_modalities(plan: ExperimentPlan) -> list[str]:
    values = {variable.modality.lower() for variable in plan.variables if variable.modality}
    values.update(str(item).lower() for item in plan.metadata.get("requested_modalities", []))
    return sorted(values)
