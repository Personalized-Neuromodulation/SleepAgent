from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sleep_ai_scientist.schemas.experiment import ExperimentPlan, ExperimentPlanStatus
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord


def _formula(outcome: str, predictors: list[str], covariates: list[str]) -> str:
    rhs = predictors + covariates
    return f"{outcome} ~ {' + '.join(rhs) if rhs else '1'}"


def hypothesis_to_plan(hypothesis: HypothesisRecord, config: dict[str, Any]) -> ExperimentPlan:
    """Convert a screened hypothesis into a prespecified draft analysis plan."""
    analysis = config.get("analysis", {})
    outcome = hypothesis.variables.dependent[0]
    predictors = list(hypothesis.variables.independent)
    covariates = list(hypothesis.variables.covariates)
    group_variable = "group" if "group" in predictors else None
    robustness = []
    rb = config.get("robustness", {})
    if rb.get("run_bootstrap", True):
        robustness.append("bootstrap")
    if rb.get("run_permutation", True):
        robustness.append("permutation")
    if rb.get("run_covariate_sensitivity", True):
        robustness.append("covariate_sensitivity")
    return ExperimentPlan(
        experiment_id=f"EXP_{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        analysis_type=analysis.get("default_model", "linear_model"),
        outcome=outcome,
        predictors=predictors,
        covariates=covariates,
        group_variable=group_variable,
        model_formula=_formula(outcome, predictors, covariates),
        quality_gates={
            "min_n_total": int(analysis.get("min_n_total", 20)),
            "min_n_per_group": int(analysis.get("min_n_per_group", 10)),
            "max_missing_rate": 0.35,
            "required_variables": [outcome] + predictors,
            "required_covariates": covariates,
        },
        correction_method=analysis.get("correction_method", "fdr_bh"),
        robustness=robustness,
        lock_status=ExperimentPlanStatus.draft,
        created_at=datetime.now(timezone.utc).isoformat(),
        locked_at=None,
        plan_hash=None,
    )
