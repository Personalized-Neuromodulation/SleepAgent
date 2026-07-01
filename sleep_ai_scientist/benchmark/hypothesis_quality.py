from __future__ import annotations

from typing import Any

from sleep_ai_scientist.benchmark.utils import analysis_ready_variables, load_hypotheses, model_dump_rows, output_path
from sleep_ai_scientist.common.io import write_csv
from sleep_ai_scientist.schemas.benchmark import HypothesisQualityScore

CAUSAL_TERMS = ("cause", "causes", "drives", "mediates", "leads to", "mechanism discovered")


def score_hypothesis_quality(hypothesis: dict[str, Any], ready_variables: set[str]) -> HypothesisQualityScore:
    used = hypothesis.get("used_data_features") or []
    variables = hypothesis.get("variables") or {}
    if not used:
        used = variables.get("independent", []) + variables.get("dependent", []) + variables.get("covariates", [])
    missing = [name for name in used if name not in ready_variables]
    evidence_level = str(hypothesis.get("evidence_level", ""))
    source = str(hypothesis.get("source", ""))
    text = f"{hypothesis.get('title', '')} {hypothesis.get('primary_prediction', '')}".lower()
    causal_risk = any(term in text for term in CAUSAL_TERMS)
    warnings = []
    if missing:
        warnings.append(f"missing_variables:{';'.join(missing)}")
    if not hypothesis.get("supporting_evidence_ids"):
        warnings.append("missing_supporting_evidence")
    if not hypothesis.get("falsification_criteria"):
        warnings.append("missing_falsification_criteria")
    if "posthoc" in source and evidence_level == "confirmatory":
        warnings.append("posthoc_confirmatory_mislabel")
    if causal_risk:
        warnings.append("causal_language_risk")
    data_score = 0.0 if missing else 1.0
    evidence_score = min(1.0, 0.25 + 0.2 * len(hypothesis.get("supporting_evidence_ids") or []))
    falsifiability = 1.0 if hypothesis.get("falsification_criteria") else 0.0
    model_score = 1.0 if hypothesis.get("analysis_models") else 0.0
    novelty = min(1.0, 0.55 + 0.12 * max(0, len(hypothesis.get("required_modalities") or []) - 1))
    clinical = 0.9 if {"ISI", "PSQI"} & set(variables.get("dependent", [])) else 0.6
    overclaim = 1.0 if causal_risk else 0.0
    mechanism = 0.85 if hypothesis.get("mechanism") else 0.4
    overall = round(
        0.20 * data_score
        + 0.20 * evidence_score
        + 0.15 * mechanism
        + 0.15 * falsifiability
        + 0.10 * novelty
        + 0.10 * clinical
        + 0.10 * (1 - overclaim),
        4,
    )
    return HypothesisQualityScore(
        hypothesis_id=hypothesis.get("hypothesis_id", ""),
        valid_variables=not missing,
        has_supporting_evidence=bool(hypothesis.get("supporting_evidence_ids")),
        has_falsification_criteria=bool(hypothesis.get("falsification_criteria")),
        has_analysis_model=bool(hypothesis.get("analysis_models")) or bool(model_score),
        evidence_level=evidence_level,
        status=str(hypothesis.get("status", "")),
        mechanism_plausibility_score=mechanism,
        data_testability_score=data_score,
        evidence_grounding_score=round(evidence_score, 4),
        falsifiability_score=falsifiability,
        novelty_proxy_score=round(novelty, 4),
        clinical_value_score=clinical,
        overclaim_risk_score=overclaim,
        overall_quality_score=overall,
        warnings=warnings,
    )


def run_hypothesis_quality_benchmark(config: dict[str, Any]) -> list[HypothesisQualityScore]:
    ready = analysis_ready_variables(config)
    scores = [score_hypothesis_quality(item, ready) for item in load_hypotheses(config)]
    write_csv(output_path(config, "hypothesis_quality_scores"), model_dump_rows(scores))
    return scores
