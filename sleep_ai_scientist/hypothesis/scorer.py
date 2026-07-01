from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_csv, read_yaml
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, HypothesisStatus

WEIGHTS = {
    "evidence_strength": 0.18,
    "data_testability": 0.18,
    "statistical_feasibility": 0.16,
    "mechanistic_plausibility": 0.14,
    "novelty_proxy": 0.12,
    "clinical_value": 0.10,
    "falsifiability": 0.06,
    "confound_controllability": 0.06,
}


def _profile_features(path: Path) -> dict[str, dict[str, Any]]:
    profile = read_yaml(path) if path.exists() else {"features": []}
    return {item["feature_name"]: item for item in profile.get("features", []) if item.get("feature_name")}


def _clip(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def score_hypothesis(hypothesis: HypothesisRecord, config: dict[str, Any]) -> HypothesisRecord:
    """Score a hypothesis before analysis; p-values and effect sizes are never used."""
    root = Path(config["_project_root"])
    inputs = config.get("inputs", {})
    features = _profile_features(resolve_path(inputs.get("analysis_ready_profile", ""), root))
    master = read_csv(resolve_path(inputs.get("master_table", ""), root)) if inputs.get("master_table") else []
    evidence_rows = read_csv(resolve_path(inputs.get("evidence_table", ""), root)) if inputs.get("evidence_table") else []
    used = [name for name in hypothesis.used_data_features if name != "group"]
    missing = [name for name in used if name not in features]
    if missing:
        hypothesis.pre_analysis_score = 0.0
        hypothesis.score_components = {key: 0.0 for key in WEIGHTS}
        hypothesis.risk_flags.append("missing_analysis_ready_variable")
        hypothesis.status = HypothesisStatus.rejected
        return hypothesis
    quality = []
    support = 0
    refute = 0
    for row in evidence_rows:
        if row.get("evidence_id") in hypothesis.supporting_evidence_ids:
            try:
                quality.append(float(row.get("evidence_quality_score") or 0.5))
            except ValueError:
                quality.append(0.5)
            support += 1 if row.get("direction") == "support" else 0
            refute += 1 if row.get("direction") == "refute" else 0
    evidence_strength = _clip((sum(quality) / len(quality) if quality else 0.45) + min(support, 3) * 0.03 - refute * 0.08)
    missing_rates = [float(features[name].get("missing_rate") or 0.0) for name in used]
    data_testability = _clip(1.0 - (sum(missing_rates) / len(missing_rates) if missing_rates else 0.0))
    n_total = len(master)
    n_available = min([int(features[name].get("n_available") or n_total) for name in used], default=n_total)
    predictors = len(hypothesis.variables.independent) + len(hypothesis.variables.covariates)
    statistical_feasibility = _clip((n_available / max(1, n_total)) - max(0, predictors - 3) * 0.05)
    preferred = set(config.get("hypothesis_priorities", {}).get("preferred_mechanisms", []))
    mechanistic_plausibility = 0.85 if hypothesis.mechanism in preferred else 0.65
    novelty_proxy = 0.55 if len(hypothesis.required_modalities) <= 1 else 0.75
    clinical_value = 0.9 if {"ISI", "PSQI"} & set(hypothesis.variables.dependent) else 0.65
    falsifiability = 1.0 if hypothesis.falsification_criteria else 0.2
    covs = set(hypothesis.variables.covariates)
    confound_controllability = 0.85 if {"age", "sex"} <= covs else 0.6
    if any(name in hypothesis.used_data_features for name in ["thalamus_DMN_FC", "DMN_FC", "salience_FC"]):
        confound_controllability = min(confound_controllability, 0.9 if "mean_FD" in covs else 0.55)
    components = {
        "evidence_strength": _clip(evidence_strength),
        "data_testability": _clip(data_testability),
        "statistical_feasibility": _clip(statistical_feasibility),
        "mechanistic_plausibility": _clip(mechanistic_plausibility),
        "novelty_proxy": _clip(novelty_proxy),
        "clinical_value": _clip(clinical_value),
        "falsifiability": _clip(falsifiability),
        "confound_controllability": _clip(confound_controllability),
    }
    hypothesis.score_components = components
    hypothesis.pre_analysis_score = round(sum(components[key] * weight for key, weight in WEIGHTS.items()), 4)
    hypothesis.status = HypothesisStatus.screened
    return hypothesis


def score_hypotheses(hypotheses: list[HypothesisRecord], config: dict[str, Any]) -> list[HypothesisRecord]:
    return [score_hypothesis(item, config) for item in hypotheses]
