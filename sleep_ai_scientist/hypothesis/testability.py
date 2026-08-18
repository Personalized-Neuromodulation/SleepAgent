from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.schemas.data_profile import DataProfile, FeatureProfile
from sleep_ai_scientist.schemas.hypothesis import Hypothesis


MODALITY_TERMS = {
    "DTI": ["dti", "diffusion tensor", "fractional anisotropy", " fa ", "white matter"],
    "fMRI": ["fmri", "functional connectivity", "resting-state", "resting state", "dmn_fc", "salience_fc", "frontoparietal_fc"],
    "EEG": ["eeg", "spindle", "slow wave", "slow-wave", "delta power", "theta power"],
    "scales": ["isi", "psqi", "sleep quality", "insomnia severity index"],
    "MRI": ["structural mri", "cortical thickness", "gray matter", "hippocampus volume"],
}

VARIABLE_TERMS = {
    "FA": ["fractional anisotropy", " fa ", "white matter integrity"],
    "DMN_FC": ["dmn_fc", "dmn functional connectivity", "default mode network"],
    "salience_FC": ["salience_fc", "salience network"],
    "frontoparietal_FC": ["frontoparietal_fc", "frontoparietal network"],
    "thalamus_DMN_FC": ["thalamus_dmn_fc", "thalamus dmn", "thalamocortical"],
    "slow_wave_density": ["slow_wave_density", "slow wave density", "slow-wave density"],
    "spindle_density": ["spindle_density", "spindle density"],
    "REM_latency": ["rem latency", "rem_latency"],
    "sleep_efficiency": ["sleep efficiency", "sleep_efficiency"],
    "NREM_duration": ["nrem duration", "nrem_duration", "nrem sleep"],
    "REM_duration": ["rem duration", "rem_duration", "rem sleep"],
    "ISI": ["insomnia severity index", " isi "],
    "PSQI": [" psqi ", "sleep quality"],
}

STATUS_BONUS = {
    "directly_testable": 40.0,
    "partially_testable": 10.0,
    "not_directly_testable": -30.0,
    "unknown": 0.0,
}


def load_analysis_ready_profile(path: str | Path | None) -> DataProfile | None:
    if not path:
        return None
    profile_path = Path(path)
    if not profile_path.exists() or profile_path.stat().st_size == 0:
        return None
    return DataProfile(**read_yaml(profile_path))


def annotate_registry_testability(registry: Any, profile: DataProfile | None) -> None:
    for hypothesis in registry.all():
        hypothesis.metadata = dict(hypothesis.metadata)
        hypothesis.metadata["data_testability"] = assess_hypothesis_testability(hypothesis, profile)
        registry.save_hypothesis(hypothesis)


def assess_hypothesis_testability(hypothesis: Hypothesis, profile: DataProfile | None) -> dict[str, Any]:
    available_features = [feature for feature in (profile.features if profile else []) if feature.approved and feature.source_file]
    available_modalities = sorted({_canonical_modality(feature.modality) for feature in available_features if feature.modality})
    available_variables = {feature.feature_name for feature in available_features}
    text = _hypothesis_text(hypothesis)
    required_modalities = _required_modalities(text)
    required_variables = _required_variables(text)
    matched_modalities = sorted(set(required_modalities) & set(available_modalities))
    missing_modalities = sorted(set(required_modalities) - set(available_modalities))
    matched_variables = sorted(variable for variable in required_variables if variable in available_variables or _has_variable_proxy(variable, available_variables))
    missing_variables = sorted(variable for variable in required_variables if variable not in matched_variables)

    if not profile or not available_features:
        status = "unknown"
        note = "No analysis-ready profile is available; current-data testability cannot be assessed."
    elif missing_modalities and not matched_variables:
        status = "not_directly_testable"
        note = "The hypothesis depends on missing modalities/variables and is not directly testable with the current foundation."
    elif missing_modalities or missing_variables:
        status = "partially_testable" if matched_variables or matched_modalities else "not_directly_testable"
        note = "The hypothesis has some measurable proxies but missing modalities/variables prevent a direct test."
    else:
        status = "directly_testable"
        note = "The hypothesis has required modalities/variables represented in the current analysis-ready profile."

    return {
        "status": status,
        "available_modalities": available_modalities,
        "required_modalities": required_modalities,
        "missing_modalities": missing_modalities,
        "matched_variables": matched_variables,
        "missing_variables": missing_variables,
        "ranking_bonus": STATUS_BONUS.get(status, 0.0),
        "note": note,
    }


def experiment_priority_score(hypothesis: Hypothesis) -> float:
    testability = hypothesis.metadata.get("data_testability", {}) if isinstance(hypothesis.metadata, dict) else {}
    preflight = hypothesis.metadata.get("experiment_preflight", {}) if isinstance(hypothesis.metadata, dict) else {}
    return (
        float(hypothesis.elo_rating)
        + float(testability.get("ranking_bonus", 0.0) or 0.0)
        + float(preflight.get("ranking_penalty", 0.0) or 0.0)
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
    return f" {' '.join(parts).lower()} "


def _required_modalities(text: str) -> list[str]:
    modalities = []
    for modality, terms in MODALITY_TERMS.items():
        if any(_contains_term(text, term) for term in terms):
            modalities.append(modality)
    return sorted(modalities)


def _required_variables(text: str) -> list[str]:
    variables = []
    for variable, terms in VARIABLE_TERMS.items():
        if any(_contains_term(text, term) for term in terms):
            variables.append(variable)
    return sorted(variables)


def _contains_term(text: str, term: str) -> bool:
    normalized_text = re.sub(r"[_\W]+", " ", text.lower())
    normalized_term = re.sub(r"[_\W]+", " ", term.lower()).strip()
    if not normalized_term:
        return False
    return f" {normalized_term} " in f" {normalized_text} "


def _canonical_modality(value: str) -> str:
    lowered = value.strip().lower()
    if lowered == "fmri":
        return "fMRI"
    if lowered == "dti":
        return "DTI"
    if lowered == "eeg":
        return "EEG"
    if lowered in {"scale", "scales"}:
        return "scales"
    if lowered == "mri":
        return "MRI"
    return value


def _has_variable_proxy(variable: str, available_variables: set[str]) -> bool:
    if variable == "FA":
        return any("FA" in item or "fractional_anisotropy" in item.lower() for item in available_variables)
    return False
