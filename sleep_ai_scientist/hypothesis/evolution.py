from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml, write_json
from sleep_ai_scientist.schemas.hypothesis import (
    EvidenceLevel,
    EvolvedHypothesisRecord,
    HypothesisRecord,
    HypothesisStatus,
    HypothesisVariables,
    RankingResult,
    ReflectionReview,
)


def _ready(config: dict[str, Any]) -> set[str]:
    root = Path(config["_project_root"])
    path = resolve_path(config.get("inputs", {})["analysis_ready_profile"], root)
    profile = read_yaml(path) if path.exists() else {"features": []}
    return {item["feature_name"] for item in profile.get("features", []) if item.get("feature_name")} | {"group"}


def evolved_to_hypothesis(evolved: EvolvedHypothesisRecord, parent: HypothesisRecord | None = None) -> HypothesisRecord:
    used = evolved.variables.independent + evolved.variables.dependent + evolved.variables.covariates
    return HypothesisRecord(
        hypothesis_id=evolved.hypothesis_id,
        title=evolved.title,
        mechanism=evolved.mechanism,
        primary_prediction=evolved.primary_prediction,
        variables=evolved.variables,
        required_modalities=evolved.required_modalities,
        analysis_models=parent.analysis_models if parent else ["linear_model"],
        expected_direction=parent.expected_direction if parent else {},
        falsification_criteria=evolved.falsification_criteria,
        risk_flags=["co_scientist_evolved"],
        evidence_level=evolved.evidence_level,
        status=evolved.status,
        source=evolved.source,
        parent_id=evolved.parent_ids[0] if evolved.parent_ids else None,
        supporting_evidence_ids=parent.supporting_evidence_ids if parent else [],
        used_data_features=used,
    )


def evolve_hypotheses(
    hypotheses: list[HypothesisRecord],
    reviews: list[ReflectionReview],
    ranking_results: list[RankingResult],
    config: dict[str, Any],
) -> list[EvolvedHypothesisRecord]:
    if not config.get("evolution", {}).get("enabled", True):
        return []
    ready = _ready(config)
    by_id = {item.hypothesis_id: item for item in hypotheses}
    review_by_id = {item.hypothesis_id: item for item in reviews}
    ranked_ids = [item.hypothesis_id for item in ranking_results if item.final_rank and item.final_rank < 9999]
    max_items = int(config.get("evolution", {}).get("max_evolved_hypotheses", 20))
    evolved: list[EvolvedHypothesisRecord] = []

    for parent_id in ranked_ids[:3]:
        parent = by_id[parent_id]
        review = review_by_id.get(parent_id)
        covariates = list(parent.variables.covariates)
        for covariate in ["age", "sex", "medication", "mean_FD", "in_scanner_sleep_time"]:
            if covariate in ready and covariate not in covariates and review and covariate in review.confound_risks:
                covariates.append(covariate)
        used = parent.variables.independent + parent.variables.dependent + covariates
        if set(used) <= ready:
            evolved.append(
                EvolvedHypothesisRecord(
                    hypothesis_id=f"{parent_id}_refine1",
                    parent_ids=[parent_id],
                    evolution_strategy="refine",
                    title=f"Refined: {parent.title}",
                    mechanism=parent.mechanism,
                    primary_prediction=f"{parent.primary_prediction} This evolved version explicitly treats confounds as exploratory covariates.",
                    variables=HypothesisVariables(independent=parent.variables.independent, dependent=parent.variables.dependent, covariates=covariates),
                    required_modalities=parent.required_modalities,
                    falsification_criteria=parent.falsification_criteria or ["The refined primary association is absent after covariate adjustment."],
                    evidence_level=EvidenceLevel.posthoc_exploratory,
                    status=HypothesisStatus.generated,
                    evolution_rationale="Refined after reflection to improve confound handling and falsifiability.",
                )
            )
        if len(evolved) >= max_items:
            break

    if len(ranked_ids) >= 2 and len(evolved) < max_items:
        a, b = by_id[ranked_ids[0]], by_id[ranked_ids[1]]
        independent = []
        for name in a.variables.independent + b.variables.independent:
            if name not in independent and name in ready:
                independent.append(name)
        dependent = [name for name in a.variables.dependent + b.variables.dependent if name in ready]
        dependent = dependent[:1] or [name for name in ["ISI", "PSQI"] if name in ready][:1]
        covariates = []
        for name in a.variables.covariates + b.variables.covariates:
            if name in ready and name not in covariates:
                covariates.append(name)
        if independent and dependent:
            evolved.append(
                EvolvedHypothesisRecord(
                    hypothesis_id=f"{a.hypothesis_id}_{b.hypothesis_id}_merge1",
                    parent_ids=[a.hypothesis_id, b.hypothesis_id],
                    evolution_strategy="merge",
                    title=f"Merged multimodal proposal: {a.mechanism} and {b.mechanism}",
                    mechanism="multimodal sleep disruption",
                    primary_prediction=f"Combined features from {a.mechanism} and {b.mechanism} are associated with {dependent[0]}.",
                    variables=HypothesisVariables(independent=independent, dependent=dependent, covariates=covariates),
                    required_modalities=sorted(set(a.required_modalities + b.required_modalities)),
                    falsification_criteria=["The merged predictor set does not improve the prespecified association with the outcome."],
                    evidence_level=EvidenceLevel.posthoc_exploratory,
                    status=HypothesisStatus.generated,
                    evolution_rationale="Merged complementary high-ranking hypotheses to preserve multimodal diversity.",
                )
            )

    if ranked_ids and len(evolved) < max_items:
        parent = by_id[ranked_ids[0]]
        if parent.variables.dependent and "ISI" in ready:
            independent = [parent.variables.dependent[0]]
            dependent = ["ISI"] if parent.variables.dependent[0] != "ISI" else ["PSQI"] if "PSQI" in ready else parent.variables.dependent
            used = independent + dependent + parent.variables.covariates
            if set(used) <= ready:
                evolved.append(
                    EvolvedHypothesisRecord(
                        hypothesis_id=f"{parent.hypothesis_id}_mutate1",
                        parent_ids=[parent.hypothesis_id],
                        evolution_strategy="mutate",
                        title=f"Mutated symptom-association variant of {parent.title}",
                        mechanism=parent.mechanism,
                        primary_prediction=f"{independent[0]} is explored as a predictor of {dependent[0]} rather than as the original outcome.",
                        variables=HypothesisVariables(independent=independent, dependent=dependent, covariates=parent.variables.covariates),
                        required_modalities=parent.required_modalities,
                        falsification_criteria=["The mutated association is absent after prespecified adjustment."],
                        evidence_level=EvidenceLevel.posthoc_exploratory,
                        status=HypothesisStatus.generated,
                        evolution_rationale="Mutated analysis direction to explore a testable symptom-association variant.",
                    )
                )
    return evolved[:max_items]


def run_evolution_agent(
    hypotheses: list[HypothesisRecord],
    reviews: list[ReflectionReview],
    ranking_results: list[RankingResult],
    config: dict[str, Any],
) -> list[EvolvedHypothesisRecord]:
    evolved = evolve_hypotheses(hypotheses, reviews, ranking_results, config)
    root = Path(config["_project_root"])
    write_json(resolve_path(config.get("outputs", {})["evolved_hypotheses"], root), [item.model_dump(mode="json") for item in evolved])
    return evolved
