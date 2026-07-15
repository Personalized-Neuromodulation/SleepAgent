from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sleep_ai_scientist.common.io import write_yaml
from sleep_ai_scientist.schemas.data_profile import DataProfile, FeatureProfile
from sleep_ai_scientist.schemas.experiment import ExperimentPlan, ExperimentVariable, ExperimentVariableRole
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
        available_features = [feature for feature in profile.features if feature.source_file and feature.approved]
        available_modalities = sorted({feature.modality.lower() for feature in available_features if feature.modality})
        requested_modalities = set(_requested_modalities(plan))
        missing_modalities = sorted(requested_modalities - set(available_modalities))
        metadata = dict(plan.metadata)
        metadata["testability_precheck"] = {
            "available_modalities": available_modalities,
            "excluded_modalities": missing_modalities,
            "full_requested_modalities_available": not missing_modalities,
            "mode": "available_modalities_only",
            "reason": "Experiment plan was rebuilt using only modalities present in the analysis-ready profile.",
        }
        if not available_features:
            plan.predictors = []
            plan.outcomes = []
            plan.covariates = []
            plan.negative_controls = []
            plan.variables = []
            plan.primary_tests = []
            metadata["testability_precheck"]["mode"] = "no_available_modalities"
            metadata["testability_precheck"]["reason"] = "No approved analysis-ready features are available."
            plan.metadata = metadata
            return plan

        selected = _select_available_plan_variables(plan, available_features)
        plan.predictors = selected["predictors"]
        plan.outcomes = selected["outcomes"]
        plan.covariates = selected["covariates"]
        plan.negative_controls = selected["negative_controls"]
        plan.variables = _variables_from_selected_features(
            available_features,
            predictors=plan.predictors,
            outcomes=plan.outcomes,
            covariates=plan.covariates,
            negative_controls=plan.negative_controls,
        )
        plan.primary_tests = [
            {
                "test_id": f"{plan.plan_id}_{predictor}_{outcome}",
                "predictor": predictor,
                "outcome": outcome,
                "question": f"Using available {', '.join(available_modalities)} features, does {predictor} relate to {outcome}?",
            }
            for predictor in plan.predictors
            for outcome in plan.outcomes
        ]
        metadata["testability_precheck"].update(
            {
                "analysis_modalities": available_modalities,
                "selected_predictors": plan.predictors,
                "selected_outcomes": plan.outcomes,
                "selected_covariates": plan.covariates,
                "selected_negative_controls": plan.negative_controls,
            }
        )
        plan.metadata = metadata
        return plan


def _select_available_plan_variables(plan: ExperimentPlan, features: list[FeatureProfile]) -> dict[str, list[str]]:
    by_name = {feature.feature_name: feature for feature in features}
    names = set(by_name)
    predictors = _unique([name for name in plan.predictors if name in names])
    if not predictors:
        predictors = _default_predictors(features)
    outcomes = _unique([name for name in plan.outcomes if name in names and name not in predictors])
    if not outcomes:
        outcomes = _default_outcomes(features, blocked=set(predictors))
    covariates = _unique([name for name in plan.covariates if name in names and name not in set(predictors) | set(outcomes)])
    if not covariates:
        covariates = _default_covariates(features, blocked=set(predictors) | set(outcomes))
    negative_controls = _unique(
        [
            name
            for name in plan.negative_controls
            if name in names and name not in set(predictors) | set(outcomes) | set(covariates)
        ]
    )
    return {
        "predictors": predictors[:4],
        "outcomes": outcomes[:2],
        "covariates": covariates[:4],
        "negative_controls": negative_controls[:2],
    }


def _default_predictors(features: list[FeatureProfile]) -> list[str]:
    names = {feature.feature_name for feature in features}
    ordered = [name for name in FMRI_MECHANISM_FEATURES if name in names]
    ordered.extend(
        feature.feature_name
        for feature in features
        if feature.role == "feature" and feature.feature_name not in ordered and feature.feature_name not in FMRI_QC_COVARIATES
    )
    return _unique(ordered)[:4]


def _default_outcomes(features: list[FeatureProfile], *, blocked: set[str]) -> list[str]:
    names = {feature.feature_name for feature in features}
    ordered = [
        feature.feature_name
        for feature in features
        if feature.role == "outcome" and feature.feature_name not in blocked
    ]
    ordered.extend(name for name in FMRI_EXPLORATORY_OUTCOMES if name in names and name not in blocked and name not in ordered)
    ordered.extend(
        feature.feature_name
        for feature in features
        if feature.role == "feature" and feature.feature_name not in blocked and feature.feature_name not in ordered
    )
    return _unique(ordered)[:2]


def _default_covariates(features: list[FeatureProfile], *, blocked: set[str]) -> list[str]:
    names = {feature.feature_name for feature in features}
    ordered = [name for name in FMRI_QC_COVARIATES if name in names and name not in blocked]
    ordered.extend(
        feature.feature_name
        for feature in features
        if feature.role == "covariate" and feature.feature_name not in blocked and feature.feature_name not in ordered
    )
    return _unique(ordered)[:4]


def _variables_from_selected_features(
    features: list[FeatureProfile],
    *,
    predictors: list[str],
    outcomes: list[str],
    covariates: list[str],
    negative_controls: list[str],
) -> list[ExperimentVariable]:
    by_name = {feature.feature_name: feature for feature in features}
    selected = [
        *[(name, ExperimentVariableRole.predictor) for name in predictors],
        *[(name, ExperimentVariableRole.outcome) for name in outcomes],
        *[(name, ExperimentVariableRole.covariate) for name in covariates],
        *[(name, ExperimentVariableRole.negative_control) for name in negative_controls],
    ]
    variables: list[ExperimentVariable] = []
    for name, role in selected:
        feature = by_name.get(name)
        if feature is None:
            continue
        variables.append(
            ExperimentVariable(
                name=name,
                role=role,
                scientific_concept=name.replace("_", " "),
                modality=feature.modality,
                source_file=feature.source_file,
                source_column=feature.source_column or feature.feature_name,
                approved=feature.approved,
                missing_rate=feature.missing_rate,
                n_available=feature.n_available,
                mapping_confidence=0.9,
                notes="Selected from available analysis-ready profile.",
            )
        )
    return variables


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


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
