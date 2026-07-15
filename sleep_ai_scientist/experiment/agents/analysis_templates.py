from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
from scipy import stats

from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.schemas.experiment import (
    ExperimentPlan,
    NegativeControlResult,
    RobustnessCheckResult,
    StatisticalTestResult,
)


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
        if subset["subject_id"].duplicated().any():
            subset = _collapse_duplicate_subject_rows(subset)
        frames.append(subset)

    if not frames:
        return pd.DataFrame()
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="subject_id", how="inner")
    return merged


def run_primary_tests(plan: ExperimentPlan) -> list[StatisticalTestResult]:
    results: list[StatisticalTestResult] = []
    for test in plan.primary_tests:
        predictor = str(test.get("predictor", ""))
        outcome = str(test.get("outcome", ""))
        test_id = str(test.get("test_id") or stable_id("primary_test", plan.plan_id, predictor, outcome))
        table = load_analysis_table(plan, {predictor, outcome})
        results.append(_spearman_result(table, test_id, predictor, outcome))
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


def _clean_pair(table: pd.DataFrame, predictor: str, outcome: str) -> pd.DataFrame:
    if table.empty or predictor not in table.columns or outcome not in table.columns:
        return pd.DataFrame(columns=[predictor, outcome])
    clean = table[["subject_id", predictor, outcome]].copy()
    clean[predictor] = pd.to_numeric(clean[predictor], errors="coerce")
    clean[outcome] = pd.to_numeric(clean[outcome], errors="coerce")
    return clean.dropna(subset=[predictor, outcome])


def _collapse_duplicate_subject_rows(frame: pd.DataFrame) -> pd.DataFrame:
    aggregations: dict[str, str] = {}
    for column in frame.columns:
        if column == "subject_id":
            continue
        aggregations[column] = "mean" if pd.api.types.is_numeric_dtype(frame[column]) else "first"
    return frame.groupby("subject_id", as_index=False).agg(aggregations)


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
