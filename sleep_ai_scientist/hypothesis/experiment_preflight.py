from __future__ import annotations

from typing import Any

from sleep_ai_scientist.experiment.agents.planning import build_experiment_plan_from_hypothesis
from sleep_ai_scientist.experiment.design_constraints import plan_signature
from sleep_ai_scientist.feature_extraction.profile_builder import TestabilityPrecheck
from sleep_ai_scientist.schemas.data_profile import DataProfile
from sleep_ai_scientist.schemas.hypothesis import Hypothesis


DUPLICATE_EXPERIMENT_PENALTY = -1000.0
RETESTED_HYPOTHESIS_PENALTY = -500.0


def annotate_registry_experiment_preflight(
    registry: Any,
    profile: DataProfile | None,
    design_constraints: dict[str, Any] | None,
) -> None:
    if profile is None:
        return
    constraints = design_constraints or {}
    avoid = {str(item) for item in constraints.get("avoid_signatures", []) if str(item)}
    for hypothesis in registry.all():
        preflight = assess_hypothesis_experiment_preflight(hypothesis, profile, constraints)
        metadata = dict(hypothesis.metadata)
        metadata["experiment_preflight"] = preflight
        hypothesis.metadata = metadata
        registry.save_hypothesis(hypothesis)


def assess_hypothesis_experiment_preflight(
    hypothesis: Hypothesis,
    profile: DataProfile,
    design_constraints: dict[str, Any] | None,
) -> dict[str, Any]:
    constraints = design_constraints or {}
    avoid = {str(item) for item in constraints.get("avoid_signatures", []) if str(item)}
    tested_hypothesis_ids = {str(item) for item in constraints.get("tested_hypothesis_ids", []) if str(item)}
    plan = build_experiment_plan_from_hypothesis(
        hypothesis,
        profile,
        max_predictors=int(constraints.get("max_predictors", 4) or 4),
        max_outcomes=int(constraints.get("max_outcomes", 2) or 2),
        design_constraints=constraints,
    )
    executable_plan = TestabilityPrecheck().run(plan, profile)
    signature = plan_signature(executable_plan)
    duplicate = bool(signature and signature in avoid)
    retested_hypothesis = hypothesis.hypothesis_id in tested_hypothesis_ids
    status = "candidate_experiment_signature_available"
    if duplicate:
        status = "duplicate_experiment_signature"
    elif retested_hypothesis:
        status = "previously_tested_hypothesis"
    return {
        "status": status,
        "signature": signature,
        "duplicates_prior_experiment": duplicate,
        "previously_tested_hypothesis": retested_hypothesis,
        "ranking_penalty": (DUPLICATE_EXPERIMENT_PENALTY if duplicate else 0.0)
        + (RETESTED_HYPOTHESIS_PENALTY if retested_hypothesis else 0.0),
        "predictors": list(executable_plan.predictors),
        "outcomes": list(executable_plan.outcomes),
        "covariates": list(executable_plan.covariates),
        "avoid_signature_count": len(avoid),
        "note": (
            "The hypothesis currently maps to an already tested executable experiment signature."
            if duplicate
            else (
                "This hypothesis has already been consumed by a prior experiment and should be deprioritized unless it produces a clearly new design."
                if retested_hypothesis
                else "The hypothesis maps to an untested executable experiment signature under current data constraints."
            )
        ),
    }
