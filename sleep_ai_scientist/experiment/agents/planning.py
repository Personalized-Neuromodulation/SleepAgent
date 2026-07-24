from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_json, read_yaml
from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.schemas.data_profile import DataProfile, FeatureProfile, VariableMappingRecord
from sleep_ai_scientist.schemas.experiment import ExperimentPlan, ExperimentVariable, ExperimentVariableRole
from sleep_ai_scientist.schemas.hypothesis import Hypothesis

FMRI_PROXY_OUTCOMES = [
    "salience_FC",
    "frontoparietal_FC",
    "DMN_FC",
    "thalamus_salience_FC",
    "thalamus_frontoparietal_FC",
    "timefreq_ALFF_0.01_0.08",
    "timefreq_fALFF_0.01_0.08_over_0.01_0.25",
]
NON_OUTCOME_FEATURES = {"subject_id", "subject", "session", "task", "run", "mean_FD", "mean_DVARS", "max_FD", "percent_high_motion"}


def load_hypotheses(path: str | Path) -> list[Hypothesis]:
    raw = read_json(Path(path))
    return [Hypothesis(**item) for item in raw]


def load_data_profile(path: str | Path) -> DataProfile:
    payload = read_yaml(Path(path))
    return DataProfile(**payload)


def load_approved_variables(path: str | Path) -> set[str]:
    payload = read_yaml(Path(path))
    if isinstance(payload, list):
        return {str(item) for item in payload}
    if isinstance(payload, dict):
        values: set[str] = set()
        for key in ("approved_variables", "features", "variables"):
            raw = payload.get(key, [])
            if isinstance(raw, list):
                values.update(str(item.get("feature_name", item.get("name", item))) if isinstance(item, dict) else str(item) for item in raw)
        return values
    return set()


def load_variable_mappings(path: str | Path) -> list[VariableMappingRecord]:
    payload = read_yaml(Path(path))
    if isinstance(payload, dict):
        records = payload.get("mappings", payload.get("records", []))
    else:
        records = payload
    return [VariableMappingRecord(**item) for item in records or [] if isinstance(item, dict)]


def build_experiment_plan_from_hypothesis(
    hypothesis: Hypothesis,
    profile: DataProfile,
    *,
    approved_variables: set[str] | None = None,
    variable_mappings: list[VariableMappingRecord] | None = None,
    max_predictors: int = 4,
    max_outcomes: int = 2,
) -> ExperimentPlan:
    feature_by_name = {feature.feature_name: feature for feature in profile.features}
    approved_variables = approved_variables or {feature.feature_name for feature in profile.features if feature.approved}
    mapping_candidates = _mapping_candidates(variable_mappings or [])
    text = _hypothesis_text(hypothesis)
    explicit = [str(item) for item in hypothesis.metadata.get("measurable_variables", []) if str(item)]

    outcomes = _select_outcomes(profile, text, max_outcomes=max_outcomes)
    predictors = _select_predictors(profile, text, explicit, mapping_candidates, outcomes, max_predictors=max_predictors)
    covariates = _select_covariates(profile, predictors, outcomes)
    negative_controls = _select_negative_controls(profile, predictors, outcomes, covariates)

    selected = [
        *[(name, ExperimentVariableRole.predictor) for name in predictors],
        *[(name, ExperimentVariableRole.outcome) for name in outcomes],
        *[(name, ExperimentVariableRole.covariate) for name in covariates],
        *[(name, ExperimentVariableRole.negative_control) for name in negative_controls],
    ]
    variables = [
        _variable_from_feature(
            feature_by_name.get(name),
            name=name,
            role=role,
            approved=name in approved_variables,
            confidence=0.9 if name in explicit else 0.65,
        )
        for name, role in selected
    ]
    primary_tests = [
        {
            "test_id": stable_id("primary_test", hypothesis.hypothesis_id, predictor, outcome),
            "predictor": predictor,
            "outcome": outcome,
            "question": f"Does {predictor} explain variation in {outcome}?",
        }
        for predictor in predictors
        for outcome in outcomes
    ]

    return ExperimentPlan(
        plan_id=stable_id("experiment_plan", hypothesis.hypothesis_id, predictors, outcomes),
        hypothesis_id=hypothesis.hypothesis_id,
        hypothesis_title=hypothesis.title,
        scientific_question=f"Test whether {hypothesis.title} is supported by available analysis-ready variables.",
        hypothesis_summary=hypothesis.summary,
        hypothesis_content=hypothesis.content,
        predictors=predictors,
        outcomes=outcomes,
        covariates=covariates,
        negative_controls=negative_controls,
        variables=variables,
        primary_tests=primary_tests,
        analysis_plan=hypothesis.experimental_plan,
        metadata={
            "source": "ExperimentDesignAgent",
            "generation_strategy": hypothesis.generation_strategy,
            "hypothesis_rating": hypothesis.elo_rating,
            "hypothesis_data_testability": hypothesis.metadata.get("data_testability", {}),
            "requested_modalities": sorted({feature.modality for feature in variables if feature.modality}),
        },
    )


def _hypothesis_text(hypothesis: Hypothesis) -> str:
    parts = [
        hypothesis.title,
        hypothesis.summary,
        hypothesis.content,
        hypothesis.rationale,
        hypothesis.experimental_plan,
        " ".join(str(item) for item in hypothesis.metadata.get("measurable_variables", [])),
    ]
    return " ".join(parts).lower()


def _mapping_candidates(records: list[VariableMappingRecord]) -> set[str]:
    values: set[str] = set()
    for record in records:
        values.update(record.approved_data_features)
        values.update(record.candidate_variables)
    return values


def _select_predictors(
    profile: DataProfile,
    text: str,
    explicit: list[str],
    mapping_candidates: set[str],
    outcomes: list[str],
    *,
    max_predictors: int,
) -> list[str]:
    scored: list[tuple[float, str]] = []
    explicit_set = set(explicit)
    for feature in profile.features:
        if feature.feature_name in outcomes or feature.role == "outcome":
            continue
        if feature.role not in {"feature", "scale"}:
            continue
        score = 0.0
        if feature.feature_name in explicit_set:
            score += 5.0
        if feature.feature_name in mapping_candidates:
            score += 2.0
        if _token_match(feature.feature_name, text):
            score += 3.0
        if feature.approved:
            score += 0.5
        if feature.n_available:
            score += min(float(feature.n_available), 100.0) / 1000.0
        if score > 0:
            scored.append((score, feature.feature_name))
    if not scored:
        scored = [(1.0, feature.feature_name) for feature in profile.features if feature.role == "feature" and feature.feature_name not in outcomes]
    return _unique([name for _, name in sorted(scored, reverse=True)])[:max_predictors]


def _select_outcomes(profile: DataProfile, text: str, *, max_outcomes: int) -> list[str]:
    outcomes = [feature.feature_name for feature in profile.features if feature.role == "outcome" and _token_match(feature.feature_name, text)]
    if not outcomes:
        outcomes = [feature.feature_name for feature in profile.features if feature.role == "outcome"]
    if not outcomes:
        names = {feature.feature_name for feature in profile.features}
        outcomes = [name for name in FMRI_PROXY_OUTCOMES if name in names]
    if not outcomes:
        outcomes = [
            feature.feature_name
            for feature in profile.features
            if feature.role in {"scale", "feature"}
            and feature.feature_name not in NON_OUTCOME_FEATURES
            and not feature.feature_name.startswith("qc_")
            and not feature.feature_name.startswith("global_signal_")
        ]
    return _unique(outcomes)[:max_outcomes]


def _select_covariates(profile: DataProfile, predictors: list[str], outcomes: list[str]) -> list[str]:
    blocked = set(predictors) | set(outcomes)
    return [feature.feature_name for feature in profile.features if feature.role == "covariate" and feature.feature_name not in blocked][:4]


def _select_negative_controls(
    profile: DataProfile,
    predictors: list[str],
    outcomes: list[str],
    covariates: list[str],
) -> list[str]:
    blocked = set(predictors) | set(outcomes) | set(covariates)
    controls = [feature.feature_name for feature in profile.features if feature.role == "scale" and feature.feature_name not in blocked]
    return controls[:2]


def _variable_from_feature(
    feature: FeatureProfile | None,
    *,
    name: str,
    role: ExperimentVariableRole,
    approved: bool,
    confidence: float,
) -> ExperimentVariable:
    return ExperimentVariable(
        name=name,
        role=role,
        scientific_concept=name.replace("_", " "),
        modality=feature.modality if feature else "",
        source_file=feature.source_file if feature else "",
        source_column=feature.source_column if feature else name,
        approved=approved or bool(feature.approved if feature else False),
        missing_rate=feature.missing_rate if feature else None,
        n_available=feature.n_available if feature else None,
        mapping_confidence=confidence if feature else 0.0,
        notes="Mapped from analysis-ready data profile." if feature else "Variable not available in data profile.",
    )


def _token_match(name: str, text: str) -> bool:
    normalized = re.sub(r"[_\W]+", " ", name.lower()).strip()
    compact = name.lower()
    return compact in text or normalized in text


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
