from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Any

import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.regression.mixed_linear_model import MixedLM

from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.schemas.experiment import (
    ExperimentPlan,
    NegativeControlResult,
    RobustnessCheckResult,
    StatisticalTestResult,
)


DEFAULT_HEALTHY_PREFIX = "sub-YZHC"
SCALE_ANCHORS = {"ISI", "PSQI", "BAI", "BDI", "SLEEPINESS"}


def load_analysis_table(plan: ExperimentPlan, required_variables: set[str] | None = None) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    variables_by_file: dict[Path, list[Any]] = {}
    for variable in plan.variables:
        if required_variables is not None and variable.name not in required_variables:
            continue
        if not variable.source_file:
            continue
        path = Path(variable.source_file)
        variables_by_file.setdefault(path, []).append(variable)

    for path, variables in variables_by_file.items():
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if "subject_id" not in frame.columns:
            frame.insert(0, "subject_id", [f"row_{idx}" for idx in range(len(frame))])
        selected = {}
        for variable in variables:
            source = _resolve_source_column(frame, variable)
            if source:
                selected[source] = variable.name
        if not selected:
            continue
        subset = frame[["subject_id", *selected.keys()]].rename(columns=selected)
        subset.insert(1, "subject", subset["subject_id"].map(_base_subject))
        frames.append(subset)

    if not frames:
        return pd.DataFrame()
    merged = frames[0]
    for frame in frames[1:]:
        keys = ["subject", "subject_id"] if _is_session_level(merged) and _is_session_level(frame) else ["subject"]
        merged = merged.merge(frame, on=keys, how="inner")
        if "subject_id_x" in merged.columns and "subject_id_y" in merged.columns:
            merged["subject_id"] = merged["subject_id_x"].where(merged["subject_id_x"].astype(str).ne(merged["subject"]), merged["subject_id_y"])
            merged = merged.drop(columns=["subject_id_x", "subject_id_y"])
    if "healthy_label" not in merged.columns:
        merged["healthy_label"] = merged["subject"].map(_healthy_label_from_subject)
    return merged


def _is_session_level(frame: pd.DataFrame) -> bool:
    if "subject_id" not in frame.columns or "subject" not in frame.columns:
        return False
    return bool(frame["subject_id"].astype(str).ne(frame["subject"].astype(str)).any())


SUPPORTED_PRIMARY_TEMPLATES = {"spearman_correlation", "linear_regression", "mixed_effects", "logistic_regression"}


def run_primary_tests(plan: ExperimentPlan, *, primary_template: str = "spearman_correlation") -> list[StatisticalTestResult]:
    results: list[StatisticalTestResult] = []
    for test in plan.primary_tests:
        predictor = str(test.get("predictor", ""))
        outcome = str(test.get("outcome", ""))
        test_id = str(test.get("test_id") or stable_id("primary_test", plan.plan_id, predictor, outcome))
        template = str(test.get("model") or primary_template or "spearman_correlation")
        table = load_analysis_table(plan, _required_variables_for_template(plan, test, predictor, outcome, template))
        result = _run_primary_template(table, test_id, predictor, outcome, template, plan, test)
        result.metadata = {
            **result.metadata,
            "clinical_group_context": _clinical_group_context(table, predictor, outcome),
        }
        results.append(result)
    _attach_group_context_fdr(results)
    return results


def run_robustness_checks(plan: ExperimentPlan, tests: list[StatisticalTestResult], *, iterations: int = 100) -> list[RobustnessCheckResult]:
    checks: list[RobustnessCheckResult] = []
    for test in tests:
        table = load_analysis_table(plan, {test.predictor, test.outcome})
        clean = _clean_pair(table, test.predictor, test.outcome)
        effects: list[float] = []
        if len(clean) >= 4:
            for idx in range(max(1, iterations)):
                sample = clean.sample(n=len(clean), replace=True, random_state=idx)
                corr = sample[test.predictor].corr(sample[test.outcome], method="spearman")
                if corr == corr:
                    effects.append(float(corr))
        ci_low, ci_high = _quantile_ci(effects)
        median = float(pd.Series(effects).median()) if effects else None
        sign_stability = _sign_stability(effects)
        checks.append(
            RobustnessCheckResult(
                check_id=stable_id("robustness", test.test_id),
                target_test_id=test.test_id,
                method="bootstrap_spearman_ci",
                n_iterations=len(effects),
                original_effect=test.effect,
                median_effect=median,
                ci_low=ci_low,
                ci_high=ci_high,
                sign_stability=sign_stability,
                passed=bool(sign_stability is not None and sign_stability >= 0.8),
                notes="Bootstrap resampling of the primary Spearman effect.",
            )
        )
    return checks


def run_negative_controls(plan: ExperimentPlan) -> list[NegativeControlResult]:
    controls: list[NegativeControlResult] = []
    for control in plan.negative_controls:
        for predictor in plan.predictors:
            table = load_analysis_table(plan, {predictor, control})
            result = _spearman_result(table, stable_id("negative_control", plan.plan_id, predictor, control), predictor, control)
            controls.append(
                NegativeControlResult(
                    control_id=result.test_id,
                    control_type="negative_control_outcome",
                    predictor=predictor,
                    outcome=control,
                    n=result.n,
                    effect=result.effect,
                    passed=bool(result.p_value is None or result.p_value >= 0.05),
                    notes="A negative control should not show a stronger nominal association.",
                )
            )
    return controls


def _resolve_source_column(frame: pd.DataFrame, variable: Any) -> str:
    modality = str(getattr(variable, "modality", "") or "").strip().lower()
    source_column = str(getattr(variable, "source_column", "") or "").strip()
    name = str(getattr(variable, "name", "") or "").strip()
    candidates = [source_column, name]
    if modality:
        normalized_modality = "fmri" if modality == "fmri" else modality
        candidates.extend(
            [
                f"{normalized_modality}_{source_column}" if source_column else "",
                f"{normalized_modality}_{name}" if name else "",
            ]
        )
    for candidate in candidates:
        if candidate and candidate in frame.columns:
            return candidate
    return ""


def _spearman_result(table: pd.DataFrame, test_id: str, predictor: str, outcome: str) -> StatisticalTestResult:
    clean = _clean_pair(table, predictor, outcome)
    if len(clean) < 3:
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="spearman_correlation",
            n=len(clean),
            passed=False,
            notes="Insufficient non-missing paired observations.",
        )
    effect, p_value = stats.spearmanr(clean[predictor], clean[outcome])
    effect = float(effect) if effect == effect else None
    p_value = float(p_value) if p_value == p_value else None
    ci_low, ci_high = _fisher_ci(effect, len(clean)) if effect is not None else (None, None)
    return StatisticalTestResult(
        test_id=test_id,
        predictor=predictor,
        outcome=outcome,
        method="spearman_correlation",
        n=len(clean),
        effect=effect,
        p_value=p_value,
        ci_low=ci_low,
        ci_high=ci_high,
        direction="positive" if effect is not None and effect > 0 else "negative" if effect is not None and effect < 0 else "",
        passed=bool(p_value is not None and p_value < 0.05),
        notes="Primary controlled template: Spearman correlation.",
    )


def _run_primary_template(
    table: pd.DataFrame,
    test_id: str,
    predictor: str,
    outcome: str,
    template: str,
    plan: ExperimentPlan,
    test: dict[str, Any],
) -> StatisticalTestResult:
    if template == "linear_regression":
        return _linear_regression_result(table, test_id, predictor, outcome, plan)
    if template == "logistic_regression":
        return _logistic_regression_result(table, test_id, predictor, outcome, plan)
    if template == "mixed_effects":
        return _mixed_effects_result(table, test_id, predictor, outcome, plan, test)
    return _spearman_result(table, test_id, predictor, outcome)


def _required_variables_for_template(
    plan: ExperimentPlan,
    test: dict[str, Any],
    predictor: str,
    outcome: str,
    template: str,
) -> set[str]:
    required = {predictor, outcome}
    if template in {"linear_regression", "logistic_regression"}:
        required.update(plan.covariates)
    if template == "mixed_effects":
        group = str(test.get("group") or _first_categorical_covariate(plan) or "")
        if group:
            required.add(group)
        required.update(value for value in plan.covariates if value != group)
    return required


def _linear_regression_result(table: pd.DataFrame, test_id: str, predictor: str, outcome: str, plan: ExperimentPlan) -> StatisticalTestResult:
    required = [predictor, outcome, *plan.covariates]
    clean = _clean_model_table(table, required)
    if len(clean) < max(4, len(plan.covariates) + 3):
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="linear_regression",
            n=len(clean),
            passed=False,
            notes="Insufficient non-missing observations for linear regression.",
        )
    try:
        x = _design_matrix(clean, [predictor, *plan.covariates])
        y = pd.to_numeric(clean[outcome], errors="coerce")
        model = sm.OLS(y, x).fit()
        effect = float(model.params.get(predictor)) if predictor in model.params else None
        p_value = float(model.pvalues.get(predictor)) if predictor in model.pvalues else None
        ci_low = ci_high = None
        if predictor in model.params:
            interval = model.conf_int().loc[predictor]
            ci_low = float(interval.iloc[0])
            ci_high = float(interval.iloc[1])
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="linear_regression",
            n=len(clean),
            effect=effect,
            p_value=p_value,
            ci_low=ci_low,
            ci_high=ci_high,
            direction="positive" if effect is not None and effect > 0 else "negative" if effect is not None and effect < 0 else "",
            passed=bool(p_value is not None and p_value < 0.05),
            notes="Primary controlled template: ordinary least squares linear regression.",
            metadata={
                "r_squared": float(model.rsquared),
                "adj_r_squared": float(model.rsquared_adj),
                "coefficients": {_display_term_name(str(key)): float(value) for key, value in model.params.items()},
                "p_values": {_display_term_name(str(key)): float(value) for key, value in model.pvalues.items()},
                "covariates": list(plan.covariates),
            },
        )
    except Exception as exc:
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="linear_regression",
            n=len(clean),
            passed=False,
            notes=f"Linear regression failed: {type(exc).__name__}: {exc}",
        )


def _logistic_regression_result(table: pd.DataFrame, test_id: str, predictor: str, outcome: str, plan: ExperimentPlan) -> StatisticalTestResult:
    required = [predictor, outcome, *plan.covariates]
    clean = _clean_model_table(table, required)
    metadata_base = {"covariates": list(plan.covariates)}
    if len(clean) < max(6, len(plan.covariates) + 4):
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="logistic_regression",
            n=len(clean),
            passed=False,
            notes="Insufficient non-missing observations for logistic regression.",
            metadata=metadata_base,
        )
    y_raw = pd.to_numeric(clean[outcome], errors="coerce")
    unique = sorted(y_raw.dropna().unique())
    metadata_base["outcome_levels"] = [float(value) for value in unique]
    if len(unique) != 2:
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="logistic_regression",
            n=len(clean),
            passed=False,
            notes="Logistic regression requires a binary outcome.",
            metadata=metadata_base,
        )
    try:
        y = y_raw.map({unique[0]: 0.0, unique[1]: 1.0})
        x = _design_matrix(clean, [predictor, *plan.covariates])
        model = sm.Logit(y, x).fit(disp=False)
        effect = float(model.params.get(predictor)) if predictor in model.params else None
        p_value = float(model.pvalues.get(predictor)) if predictor in model.pvalues else None
        ci_low = ci_high = None
        if predictor in model.params:
            interval = model.conf_int().loc[predictor]
            ci_low = float(interval.iloc[0])
            ci_high = float(interval.iloc[1])
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="logistic_regression",
            n=len(clean),
            effect=effect,
            p_value=p_value,
            ci_low=ci_low,
            ci_high=ci_high,
            direction="positive" if effect is not None and effect > 0 else "negative" if effect is not None and effect < 0 else "",
            passed=bool(p_value is not None and p_value < 0.05),
            notes="Primary controlled template: logistic regression for a binary outcome.",
            metadata={
                **metadata_base,
                "coefficients": {_display_term_name(str(key)): float(value) for key, value in model.params.items()},
                "odds_ratios": {_display_term_name(str(key)): _safe_exp(float(value)) for key, value in model.params.items()},
                "p_values": {_display_term_name(str(key)): float(value) for key, value in model.pvalues.items()},
                "pseudo_r_squared": float(model.prsquared),
            },
        )
    except Exception as exc:
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="logistic_regression",
            n=len(clean),
            passed=False,
            notes=f"Logistic regression failed: {type(exc).__name__}: {exc}",
            metadata=metadata_base,
        )


def _mixed_effects_result(
    table: pd.DataFrame,
    test_id: str,
    predictor: str,
    outcome: str,
    plan: ExperimentPlan,
    test: dict[str, Any],
) -> StatisticalTestResult:
    group = str(test.get("group") or _first_categorical_covariate(plan) or "")
    fixed_covariates = [value for value in plan.covariates if value != group]
    required = [predictor, outcome, group, *fixed_covariates] if group else [predictor, outcome, *fixed_covariates]
    clean = _clean_model_table(table, required)
    if not group or group not in clean.columns:
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="mixed_effects",
            n=len(clean),
            passed=False,
            notes="Mixed effects model requires a group variable.",
        )
    if clean[group].nunique() < 2 or len(clean) < max(6, len(fixed_covariates) + 4):
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="mixed_effects",
            n=len(clean),
            passed=False,
            notes="Insufficient groups or observations for mixed effects model.",
            metadata={"group_variable": group},
        )
    try:
        x = _design_matrix(clean, [predictor, *fixed_covariates])
        y = pd.to_numeric(clean[outcome], errors="coerce")
        model = MixedLM(y, x, groups=clean[group]).fit(reml=False, method="lbfgs", disp=False)
        effect = float(model.params.get(predictor)) if predictor in model.params else None
        p_value = float(model.pvalues.get(predictor)) if predictor in model.pvalues else None
        ci_low = ci_high = None
        if predictor in model.params:
            interval = model.conf_int().loc[predictor]
            ci_low = float(interval.iloc[0])
            ci_high = float(interval.iloc[1])
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="mixed_effects",
            n=len(clean),
            effect=effect,
            p_value=p_value,
            ci_low=ci_low,
            ci_high=ci_high,
            direction="positive" if effect is not None and effect > 0 else "negative" if effect is not None and effect < 0 else "",
            passed=bool(p_value is not None and p_value < 0.05),
            notes="Primary controlled template: mixed effects model with random intercept.",
            metadata={
                "group_variable": group,
                "group_count": int(clean[group].nunique()),
                "fixed_effects": {_display_term_name(str(key)): float(value) for key, value in model.params.items() if key != "Group Var"},
                "p_values": {_display_term_name(str(key)): float(value) for key, value in model.pvalues.items()},
            },
        )
    except Exception as exc:
        return StatisticalTestResult(
            test_id=test_id,
            predictor=predictor,
            outcome=outcome,
            method="mixed_effects",
            n=len(clean),
            passed=False,
            notes=f"Mixed effects model failed: {type(exc).__name__}: {exc}",
            metadata={"group_variable": group},
        )


def _clean_pair(table: pd.DataFrame, predictor: str, outcome: str) -> pd.DataFrame:
    if table.empty or predictor not in table.columns or outcome not in table.columns:
        return pd.DataFrame(columns=[predictor, outcome])
    clean = table[["subject_id", predictor, outcome]].copy()
    clean[predictor] = pd.to_numeric(clean[predictor], errors="coerce")
    clean[outcome] = pd.to_numeric(clean[outcome], errors="coerce")
    return clean.dropna(subset=[predictor, outcome])


def _clean_model_table(table: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    columns = [column for column in columns if column]
    if table.empty or any(column not in table.columns for column in columns):
        return pd.DataFrame(columns=["subject_id", *columns])
    clean = table[["subject_id", *columns]].copy()
    for column in columns:
        if column == "subject_id":
            continue
        converted = pd.to_numeric(clean[column], errors="coerce")
        if converted.notna().any():
            clean[column] = converted
    return clean.dropna(subset=columns)


def _clinical_group_context(table: pd.DataFrame, predictor: str, outcome: str) -> dict[str, Any]:
    if table.empty or "healthy_label" not in table.columns:
        return {"task": "healthy_vs_nonhealthy_context", "status": "unavailable", "reason": "missing_healthy_label"}
    healthy_label = pd.to_numeric(table["healthy_label"], errors="coerce")
    clean = table.assign(healthy_label=healthy_label).dropna(subset=["healthy_label"])
    n_healthy = int((clean["healthy_label"] == 1).sum())
    n_nonhealthy = int((clean["healthy_label"] == 0).sum())
    predictor_stats = _group_difference_stats(clean, predictor, is_scale_anchor=False)
    outcome_stats = _group_difference_stats(clean, outcome, is_scale_anchor=_is_scale_anchor(outcome))
    within_group = _within_group_associations(clean, predictor, outcome)
    group_specific_models = _group_specific_models(clean, predictor, outcome)
    return {
        "task": "healthy_vs_nonhealthy_context",
        "status": "run" if n_healthy and n_nonhealthy else "insufficient_groups",
        "healthy_label_rule": f"subject_id starts with {DEFAULT_HEALTHY_PREFIX}",
        "n_healthy": n_healthy,
        "n_nonhealthy": n_nonhealthy,
        "predictor_group_difference": predictor_stats,
        "outcome_group_difference": outcome_stats,
        "within_group_associations": within_group,
        "group_specific_models": group_specific_models,
        "clinical_interpretation": _clinical_interpretation(predictor_stats, outcome_stats),
    }


def _group_difference_stats(table: pd.DataFrame, variable: str, *, is_scale_anchor: bool) -> dict[str, Any]:
    base = {
        "variable": variable,
        "is_scale_anchor": is_scale_anchor,
        "healthy_mean": None,
        "nonhealthy_mean": None,
        "nonhealthy_minus_healthy": None,
        "welch_p": None,
        "fdr_q": None,
        "direction": "unknown",
        "n_healthy": 0,
        "n_nonhealthy": 0,
    }
    if variable not in table.columns:
        return {**base, "status": "missing_variable"}
    values = pd.to_numeric(table[variable], errors="coerce")
    healthy = values[table["healthy_label"] == 1].dropna()
    nonhealthy = values[table["healthy_label"] == 0].dropna()
    base["n_healthy"] = int(len(healthy))
    base["n_nonhealthy"] = int(len(nonhealthy))
    if healthy.empty or nonhealthy.empty:
        return {**base, "status": "insufficient_groups"}
    healthy_mean = float(healthy.mean())
    nonhealthy_mean = float(nonhealthy.mean())
    diff = nonhealthy_mean - healthy_mean
    return {
        **base,
        "status": "run",
        "healthy_mean": healthy_mean,
        "nonhealthy_mean": nonhealthy_mean,
        "nonhealthy_minus_healthy": float(diff),
        "welch_p": _welch_p_value(healthy, nonhealthy),
        "direction": "nonhealthy_greater" if diff > 0 else "nonhealthy_lower" if diff < 0 else "no_difference",
    }


def _within_group_associations(table: pd.DataFrame, predictor: str, outcome: str) -> dict[str, Any]:
    healthy = _group_association(table, predictor, outcome, healthy_label=1)
    nonhealthy = _group_association(table, predictor, outcome, healthy_label=0)
    effect_difference = None
    if healthy.get("effect") is not None and nonhealthy.get("effect") is not None:
        effect_difference = float(nonhealthy["effect"] - healthy["effect"])
    return {
        "method": "spearman_correlation",
        "healthy": healthy,
        "nonhealthy": nonhealthy,
        "effect_difference_hint": effect_difference,
        "interpretation": _within_group_association_interpretation(healthy, nonhealthy),
    }


def _group_association(table: pd.DataFrame, predictor: str, outcome: str, *, healthy_label: int) -> dict[str, Any]:
    base = {
        "group": "healthy" if healthy_label == 1 else "nonhealthy",
        "n": 0,
        "effect": None,
        "p_value": None,
        "direction": "unknown",
        "status": "insufficient_observations",
    }
    if predictor not in table.columns or outcome not in table.columns:
        return {**base, "status": "missing_variable"}
    group = table[table["healthy_label"] == healthy_label]
    clean = _clean_pair(group, predictor, outcome)
    base["n"] = int(len(clean))
    if len(clean) < 3:
        return base
    effect, p_value = stats.spearmanr(clean[predictor], clean[outcome])
    effect = float(effect) if effect == effect else None
    p_value = float(p_value) if p_value == p_value else None
    return {
        **base,
        "status": "run",
        "effect": effect,
        "p_value": p_value,
        "direction": "positive" if effect is not None and effect > 0 else "negative" if effect is not None and effect < 0 else "no_association",
    }


def _within_group_association_interpretation(healthy: dict[str, Any], nonhealthy: dict[str, Any]) -> str:
    healthy_run = healthy.get("status") == "run"
    nonhealthy_run = nonhealthy.get("status") == "run"
    if not healthy_run and not nonhealthy_run:
        return "insufficient_within_group_data"
    healthy_sig = healthy.get("p_value") is not None and float(healthy["p_value"]) < 0.05
    nonhealthy_sig = nonhealthy.get("p_value") is not None and float(nonhealthy["p_value"]) < 0.05
    if nonhealthy_sig and not healthy_sig:
        return "association_specific_to_nonhealthy"
    if healthy_sig and not nonhealthy_sig:
        return "association_specific_to_healthy"
    if healthy_sig and nonhealthy_sig:
        return "association_present_in_both_groups"
    return "no_nominal_within_group_association"


def _group_specific_models(table: pd.DataFrame, predictor: str, outcome: str) -> dict[str, Any]:
    healthy = _group_linear_model(table, predictor, outcome, healthy_label=1)
    nonhealthy = _group_linear_model(table, predictor, outcome, healthy_label=0)
    interaction = _group_interaction_model(table, predictor, outcome)
    return {
        "model": "linear_regression_by_health_group",
        "healthy": healthy,
        "nonhealthy": nonhealthy,
        "interaction": interaction,
    }


def _group_linear_model(table: pd.DataFrame, predictor: str, outcome: str, *, healthy_label: int) -> dict[str, Any]:
    base = {
        "group": "healthy" if healthy_label == 1 else "nonhealthy",
        "n": 0,
        "slope": None,
        "intercept": None,
        "p_value": None,
        "r_squared": None,
        "status": "insufficient_observations",
    }
    if predictor not in table.columns or outcome not in table.columns:
        return {**base, "status": "missing_variable"}
    group = table[table["healthy_label"] == healthy_label]
    clean = _clean_pair(group, predictor, outcome)
    base["n"] = int(len(clean))
    if len(clean) < 3 or clean[predictor].nunique() < 2:
        return base
    try:
        x = sm.add_constant(pd.to_numeric(clean[predictor], errors="coerce"))
        y = pd.to_numeric(clean[outcome], errors="coerce")
        model = sm.OLS(y, x).fit()
        return {
            **base,
            "status": "run",
            "slope": _finite_float(model.params.get(predictor)),
            "intercept": _finite_float(model.params.get("const")),
            "p_value": _finite_float(model.pvalues.get(predictor)),
            "r_squared": _finite_float(model.rsquared),
        }
    except Exception:
        return {**base, "status": "failed"}


def _group_interaction_model(table: pd.DataFrame, predictor: str, outcome: str) -> dict[str, Any]:
    base = {
        "model": "outcome ~ predictor + healthy_label + predictor:healthy_label",
        "n": 0,
        "nonhealthy_slope": None,
        "healthy_slope": None,
        "slope_difference_healthy_minus_nonhealthy": None,
        "p_value": None,
        "r_squared": None,
        "status": "insufficient_observations",
        "interpretation": "insufficient_group_specific_data",
    }
    if predictor not in table.columns or outcome not in table.columns or "healthy_label" not in table.columns:
        return {**base, "status": "missing_variable"}
    clean = table[[predictor, outcome, "healthy_label"]].copy()
    clean[predictor] = pd.to_numeric(clean[predictor], errors="coerce")
    clean[outcome] = pd.to_numeric(clean[outcome], errors="coerce")
    clean["healthy_label"] = pd.to_numeric(clean["healthy_label"], errors="coerce")
    clean = clean.dropna()
    base["n"] = int(len(clean))
    if len(clean) < 6 or clean["healthy_label"].nunique() < 2 or clean[predictor].nunique() < 2:
        return base
    clean["predictor_x_healthy_label"] = clean[predictor] * clean["healthy_label"]
    try:
        x = sm.add_constant(clean[[predictor, "healthy_label", "predictor_x_healthy_label"]])
        y = clean[outcome]
        model = sm.OLS(y, x).fit()
        nonhealthy_slope = _finite_float(model.params.get(predictor))
        interaction = _finite_float(model.params.get("predictor_x_healthy_label"))
        healthy_slope = None if nonhealthy_slope is None or interaction is None else float(nonhealthy_slope + interaction)
        p_value = _finite_float(model.pvalues.get("predictor_x_healthy_label"))
        return {
            **base,
            "status": "run",
            "nonhealthy_slope": nonhealthy_slope,
            "healthy_slope": healthy_slope,
            "slope_difference_healthy_minus_nonhealthy": interaction,
            "p_value": p_value,
            "r_squared": _finite_float(model.rsquared),
            "interpretation": "group_specific_slope_difference" if p_value is not None and p_value < 0.05 else "no_nominal_slope_difference",
        }
    except Exception:
        return {**base, "status": "failed"}


def _attach_group_context_fdr(results: list[StatisticalTestResult]) -> None:
    predictor_p: list[float | None] = []
    outcome_p: list[float | None] = []
    contexts: list[dict[str, Any]] = []
    for result in results:
        context = result.metadata.get("clinical_group_context", {})
        contexts.append(context)
        predictor_p.append((context.get("predictor_group_difference") or {}).get("welch_p"))
        outcome_p.append((context.get("outcome_group_difference") or {}).get("welch_p"))
    predictor_q = _benjamini_hochberg(predictor_p)
    outcome_q = _benjamini_hochberg(outcome_p)
    for context, pred_q, out_q in zip(contexts, predictor_q, outcome_q, strict=False):
        if isinstance(context.get("predictor_group_difference"), dict):
            context["predictor_group_difference"]["fdr_q"] = pred_q
        if isinstance(context.get("outcome_group_difference"), dict):
            context["outcome_group_difference"]["fdr_q"] = out_q


def _clinical_interpretation(predictor_stats: dict[str, Any], outcome_stats: dict[str, Any]) -> str:
    predictor_diff = predictor_stats.get("nonhealthy_minus_healthy")
    outcome_diff = outcome_stats.get("nonhealthy_minus_healthy")
    if predictor_diff is None or outcome_diff is None:
        return "insufficient_group_context"
    if predictor_diff != 0 and outcome_diff != 0 and bool(outcome_stats.get("is_scale_anchor")):
        return "fc_and_scale_both_different_between_groups"
    if predictor_diff != 0:
        return "fc_differs_between_groups"
    if outcome_diff != 0 and bool(outcome_stats.get("is_scale_anchor")):
        return "scale_differs_between_groups"
    return "no_group_difference_context"


def _is_scale_anchor(variable: str) -> bool:
    return variable.strip().upper() in SCALE_ANCHORS


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _healthy_label_from_subject(subject_id: Any) -> int:
    return 1 if str(subject_id).startswith(DEFAULT_HEALTHY_PREFIX) else 0


def _welch_p_value(healthy: pd.Series, nonhealthy: pd.Series) -> float | None:
    if len(healthy) < 2 or len(nonhealthy) < 2:
        return None
    _, p_value = stats.ttest_ind(nonhealthy, healthy, equal_var=False, nan_policy="omit")
    return float(p_value) if p_value == p_value else None


def _benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    indexed = [(idx, float(p)) for idx, p in enumerate(p_values) if p is not None and p == p]
    q_values: list[float | None] = [None] * len(p_values)
    if not indexed:
        return q_values
    indexed.sort(key=lambda item: item[1])
    m = len(indexed)
    previous = 1.0
    for rank, (idx, p_value) in reversed(list(enumerate(indexed, start=1))):
        q_value = min(previous, p_value * m / rank)
        q_values[idx] = float(min(q_value, 1.0))
        previous = q_value
    return q_values


def _design_matrix(clean: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    frames: list[pd.Series | pd.DataFrame] = []
    for column in columns:
        series = clean[column]
        if pd.api.types.is_numeric_dtype(series):
            frames.append(pd.to_numeric(series, errors="coerce").rename(column))
        else:
            frames.append(pd.get_dummies(series.astype(str), prefix=column, drop_first=True, dtype=float))
    x = pd.concat(frames, axis=1) if frames else pd.DataFrame(index=clean.index)
    return sm.add_constant(x, has_constant="add")


def _first_categorical_covariate(plan: ExperimentPlan) -> str:
    for variable in plan.variables:
        if variable.role == "covariate" and variable.name in plan.covariates:
            name = variable.name.lower()
            if any(token in name for token in ["site", "group", "subject", "session", "scanner"]):
                return variable.name
    for covariate in plan.covariates:
        name = covariate.lower()
        if any(token in name for token in ["site", "group", "subject", "session", "scanner"]):
            return covariate
    return ""


def _display_term_name(name: str) -> str:
    return "Intercept" if name == "const" else name


def _safe_exp(value: float) -> float:
    return float(math.exp(max(min(value, 50.0), -50.0)))


def _collapse_duplicate_subject_rows(frame: pd.DataFrame) -> pd.DataFrame:
    aggregations: dict[str, str] = {}
    for column in frame.columns:
        if column == "subject_id":
            continue
        aggregations[column] = "mean" if pd.api.types.is_numeric_dtype(frame[column]) else "first"
    return frame.groupby("subject_id", as_index=False).agg(aggregations)


def _base_subject(value: Any) -> str:
    match = re.search(r"(sub-[A-Za-z0-9]+)", str(value))
    return match.group(1) if match else str(value)


def _fisher_ci(effect: float, n: int) -> tuple[float | None, float | None]:
    if n <= 3 or abs(effect) >= 1:
        return None, None
    z = math.atanh(effect)
    se = 1 / math.sqrt(n - 3)
    return math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)


def _quantile_ci(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    series = pd.Series(values)
    return float(series.quantile(0.025)), float(series.quantile(0.975))


def _sign_stability(values: list[float]) -> float | None:
    if not values:
        return None
    positives = sum(1 for value in values if value >= 0)
    negatives = len(values) - positives
    return max(positives, negatives) / len(values)
