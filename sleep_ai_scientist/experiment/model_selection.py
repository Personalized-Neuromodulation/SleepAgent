from __future__ import annotations

from typing import Any

import pandas as pd

from sleep_ai_scientist.experiment.agents.analysis_templates import SUPPORTED_PRIMARY_TEMPLATES, load_analysis_table
from sleep_ai_scientist.schemas.experiment import ExperimentPlan


GROUP_TERMS = {"site", "scanner", "session", "subject", "participant", "group", "batch", "cohort"}
MOTION_COVARIATES = {"mean_fd", "mean_dvars", "max_fd", "percent_high_motion"}
DEFAULT_ML_MODELS = ["logistic_regression", "decision_tree", "random_forest", "svm", "xgboost", "lightgbm"]


def select_primary_model(
    plan: ExperimentPlan,
    *,
    configured_template: str = "auto",
    model_review: dict[str, Any] | None = None,
    configured_ml_models: list[str] | None = None,
) -> dict[str, Any]:
    configured = (configured_template or "auto").strip()
    required = set(plan.predictors) | set(plan.outcomes) | set(plan.covariates)
    table = load_analysis_table(plan, required)
    n_rows = int(len(table)) if not table.empty else 0
    outcome = plan.outcomes[0] if plan.outcomes else ""
    modalities = sorted({str(variable.modality) for variable in plan.variables if variable.modality})
    group = _group_variable(plan, table)
    binary = _is_binary_outcome(table, outcome)
    motion_covariates = sorted(covariate for covariate in plan.covariates if covariate.lower() in MOTION_COVARIATES)
    ml_models = list(configured_ml_models or DEFAULT_ML_MODELS)
    run_ml = _should_run_ml(plan, n_rows=n_rows, binary=binary)
    ml_reason = _ml_reason(plan, n_rows=n_rows, binary=binary) if run_ml else "Inferential statistical template is sufficient for this simple low-dimensional test."
    ml_task_type = "classification" if binary else "regression"
    common = {
        "n_rows": n_rows,
        "modalities": modalities,
        "group_variable": group,
        "motion_covariates": motion_covariates,
        "candidate_models": _candidate_models(ml_task_type, ml_models),
        "run_ml": run_ml,
        "ml_task_type": ml_task_type,
        "ml_reason": ml_reason,
    }

    if configured and configured != "auto":
        return _decision(
            configured,
            reason="Manual primary_template override from experiment config; ML eligibility is still evaluated by policy.",
            plan=plan,
            source="config_override",
            outcome_type="binary" if binary else "continuous_or_ranked",
            **common,
        )

    if binary:
        return _decision(
            "logistic_regression",
            reason="Binary outcome detected; logistic regression is the primary controlled template.",
            plan=plan,
            source="rule",
            outcome_type="binary",
            **common,
        )
    if group:
        return _decision(
            "mixed_effects",
            reason=f"Grouped experimental structure detected via {group}; mixed effects controls group-level dependence.",
            plan=plan,
            source="rule",
            outcome_type="continuous_or_ranked",
            **common,
        )
    if plan.covariates:
        reason = "Covariates are available; linear regression can estimate the predictor effect while controlling confounds."
        if motion_covariates:
            reason = f"fMRI/QC motion covariates available ({', '.join(motion_covariates)}); linear regression controls confounding."
        return _decision(
            "linear_regression",
            reason=reason,
            plan=plan,
            source="rule",
            outcome_type="continuous_or_ranked",
            **common,
        )

    recommended = str((model_review or {}).get("recommended_primary_template", "") or "").strip()
    if recommended in SUPPORTED_PRIMARY_TEMPLATES:
        return _decision(
            recommended,
            reason="LLM recommended a supported primary template and no stronger rule overrode it.",
            plan=plan,
            source="llm_recommendation",
            outcome_type="binary" if binary else "continuous_or_ranked",
            **common,
        )

    return _decision(
        "spearman_correlation",
        reason="No binary outcome, grouping structure, or covariates were detected; Spearman is the conservative exploratory fallback.",
        plan=plan,
        source="fallback",
        outcome_type="continuous_or_ranked",
        **common,
    )


def _decision(primary_template: str, *, reason: str, plan: ExperimentPlan, source: str, **extra: Any) -> dict[str, Any]:
    return {
        "primary_template": primary_template,
        "source": source,
        "reason": reason,
        "plan_id": plan.plan_id,
        "predictors": list(plan.predictors),
        "outcomes": list(plan.outcomes),
        "covariates": list(plan.covariates),
        **extra,
    }


def _group_variable(plan: ExperimentPlan, table: pd.DataFrame) -> str:
    explicit = [str(test.get("group", "")) for test in plan.primary_tests if isinstance(test, dict) and test.get("group")]
    candidates = [*explicit, *plan.covariates]
    for candidate in candidates:
        lowered = candidate.lower()
        if not any(term in lowered for term in GROUP_TERMS):
            continue
        if table.empty or candidate not in table.columns:
            return candidate
        values = table[candidate].dropna()
        if values.nunique() >= 2 and len(values) >= 6:
            return candidate
    return ""


def _is_binary_outcome(table: pd.DataFrame, outcome: str) -> bool:
    if table.empty or not outcome or outcome not in table.columns:
        return False
    values = pd.to_numeric(table[outcome], errors="coerce").dropna().unique()
    if len(values) != 2:
        return False
    return all(float(value).is_integer() for value in values)


def _should_run_ml(plan: ExperimentPlan, *, n_rows: int, binary: bool) -> bool:
    if n_rows < 4 or not plan.predictors or not plan.outcomes:
        return False
    if binary:
        return True
    if len(plan.predictors) >= 2:
        return True
    return False


def _ml_reason(plan: ExperimentPlan, *, n_rows: int, binary: bool) -> str:
    if binary:
        return "Binary outcome detected; classification models are eligible under the model-selection policy."
    if len(plan.predictors) >= 2:
        return "Multiple predictors are available; predictive ML regressors are eligible under the model-selection policy."
    return f"ML eligibility satisfied with n={n_rows}."


def _candidate_models(task_type: str, configured: list[str]) -> list[str]:
    candidates = []
    for name in configured:
        normalized = name.strip().lower()
        if not normalized:
            continue
        if normalized == "logistic_regression" and task_type == "classification":
            candidates.append("logistic_regression")
        elif normalized == "decision_tree":
            candidates.append("decision_tree_classifier" if task_type == "classification" else "decision_tree_regressor")
        elif normalized == "random_forest":
            candidates.append("random_forest_classifier" if task_type == "classification" else "random_forest_regressor")
        elif normalized == "svm":
            candidates.append("svm_classifier" if task_type == "classification" else "svm_regressor")
        elif normalized == "xgboost":
            candidates.append("xgboost_classifier" if task_type == "classification" else "xgboost_regressor")
        elif normalized == "lightgbm":
            candidates.append("lightgbm_classifier" if task_type == "classification" else "lightgbm_regressor")
        elif normalized.endswith("_classifier") and task_type == "classification":
            candidates.append(normalized)
        elif normalized.endswith("_regressor") and task_type == "regression":
            candidates.append(normalized)
    return list(dict.fromkeys(candidates))
