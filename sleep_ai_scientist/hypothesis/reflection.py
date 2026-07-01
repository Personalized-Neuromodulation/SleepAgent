from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml, write_json
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, ReflectionReview

CAUSAL_TERMS = ("cause", "causes", "drives", "mediates", "mechanism discovered", "leads to")


def analysis_ready_variables(config: dict[str, Any]) -> set[str]:
    root = Path(config["_project_root"])
    path = resolve_path(config.get("inputs", {})["analysis_ready_profile"], root)
    profile = read_yaml(path) if path.exists() else {"features": []}
    return {item["feature_name"] for item in profile.get("features", []) if item.get("feature_name")} | {"group"}


def reflect_hypothesis(hypothesis: HypothesisRecord, config: dict[str, Any]) -> ReflectionReview:
    ready = analysis_ready_variables(config)
    used = set(hypothesis.used_data_features or hypothesis.variables.independent + hypothesis.variables.dependent + hypothesis.variables.covariates)
    unsupported = sorted(name for name in used if name not in ready)
    text = f"{hypothesis.title} {hypothesis.primary_prediction}".lower()
    causal_risk = any(term in text for term in CAUSAL_TERMS)
    missing_evidence = [] if hypothesis.supporting_evidence_ids else ["No supporting evidence IDs linked to hypothesis."]
    falsifiability = 1.0 if hypothesis.falsification_criteria else 0.2
    data_score = 0.0 if unsupported else 1.0
    evidence_score = min(1.0, 0.4 + 0.15 * len(hypothesis.supporting_evidence_ids)) if hypothesis.supporting_evidence_ids else 0.25
    novelty = 0.65 + min(0.25, 0.08 * max(0, len(hypothesis.required_modalities) - 1))
    covs = set(hypothesis.variables.covariates)
    confound_risks = []
    if "age" not in covs:
        confound_risks.append("age")
    if "sex" not in covs:
        confound_risks.append("sex")
    if any(name in used for name in {"thalamus_DMN_FC", "DMN_FC", "salience_FC"}) and "mean_FD" not in covs:
        confound_risks.append("mean_FD")
    if any(name in used for name in {"slow_wave_density", "spindle_density"}) and "in_scanner_sleep_time" not in covs:
        confound_risks.append("in_scanner_sleep_time")
    if "medication" not in covs and {"ISI", "PSQI", "beta_power"} & used:
        confound_risks.append("medication")
    confound_score = max(0.0, 1.0 - 0.16 * len(set(confound_risks)))
    overall = round(
        0.25 * data_score
        + 0.25 * evidence_score
        + 0.20 * falsifiability
        + 0.15 * novelty
        + 0.15 * confound_score,
        4,
    )
    weaknesses = []
    if unsupported:
        weaknesses.append("Uses variables unavailable in analysis-ready profile.")
    if missing_evidence:
        weaknesses.append("Evidence grounding is weak.")
    if not hypothesis.falsification_criteria:
        weaknesses.append("Missing falsification criteria.")
    if confound_risks:
        weaknesses.append("Confound control requires review.")
    if causal_risk:
        weaknesses.append("Causal language risk detected.")
    if unsupported or (causal_risk and not hypothesis.falsification_criteria):
        recommendation = "reject"
    elif overall >= 0.78 and not confound_risks:
        recommendation = "keep"
    elif overall < 0.45:
        recommendation = "hold"
    else:
        recommendation = "revise"
    return ReflectionReview(
        hypothesis_id=hypothesis.hypothesis_id,
        review_id=f"REF_{hypothesis.hypothesis_id}",
        strengths=["Uses analysis-ready variables."] if not unsupported else [],
        weaknesses=weaknesses,
        missing_evidence=missing_evidence,
        unsupported_variables=unsupported,
        confound_risks=sorted(set(confound_risks)),
        causal_language_risk=causal_risk,
        alternative_explanations=[
            "Observed associations may reflect medication, motion, age, sex, or sleep-state differences.",
            "Cross-sectional data cannot establish directionality.",
        ],
        falsifiability_score=round(falsifiability, 4),
        data_grounding_score=round(data_score, 4),
        evidence_grounding_score=round(evidence_score, 4),
        novelty_score=round(novelty, 4),
        overall_reflection_score=overall,
        recommendation=recommendation,
    )


def run_reflection_agent(hypotheses: list[HypothesisRecord], config: dict[str, Any]) -> list[ReflectionReview]:
    reviews = [reflect_hypothesis(item, config) for item in hypotheses]
    root = Path(config["_project_root"])
    write_json(resolve_path(config.get("outputs", {})["reflection_reviews"], root), [item.model_dump(mode="json") for item in reviews])
    return reviews
