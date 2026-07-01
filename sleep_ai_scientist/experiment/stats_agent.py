from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_csv, read_json, write_csv, write_json
from sleep_ai_scientist.schemas.result import AnalysisResult


def _float_or_none(value: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _encode(values: list[str]) -> tuple[list[float | None], dict[str, float]]:
    numeric = [_float_or_none(item) for item in values]
    non_empty = [item for item in values if item not in ("", None)]
    if all(_float_or_none(item) is not None for item in non_empty):
        return numeric, {}
    categories = sorted({item for item in values if item not in ("", None)})
    mapping = {name: float(index) for index, name in enumerate(categories)}
    return [mapping.get(item) if item not in ("", None) else None for item in values], mapping


def _bh(p_values: dict[str, float]) -> dict[str, float]:
    items = sorted(p_values.items(), key=lambda item: item[1])
    m = max(1, len(items))
    adjusted: dict[str, float] = {}
    running = 1.0
    for rank, (key, p_value) in reversed(list(enumerate(items, start=1))):
        running = min(running, p_value * m / rank)
        adjusted[key] = round(min(1.0, running), 6)
    return adjusted


def run_locked_plan(plan_payload: dict[str, Any], config: dict[str, Any]) -> AnalysisResult:
    """Run a minimal linear model for a locked plan."""
    try:
        import numpy as np
    except ModuleNotFoundError:
        return AnalysisResult(
            experiment_id=plan_payload["experiment_id"],
            hypothesis_id=plan_payload["hypothesis_id"],
            model_formula=plan_payload["model_formula"],
            n_total=0,
            n_used=0,
            warnings=["numpy_not_available"],
            status="failed",
        )
    root = Path(config["_project_root"])
    master_path = resolve_path(config.get("inputs", {})["master_table"], root)
    rows = read_csv(master_path) if master_path.exists() else []
    predictors = list(plan_payload.get("predictors", [])) + list(plan_payload.get("covariates", []))
    outcome = plan_payload["outcome"]
    required = [outcome] + predictors
    encoded: dict[str, list[float | None]] = {}
    warnings: list[str] = []
    for name in required:
        values, mapping = _encode([row.get(name, "") for row in rows])
        if mapping:
            warnings.append(f"encoded_categorical:{name}")
        encoded[name] = values
    kept = []
    for i in range(len(rows)):
        if all(encoded[name][i] is not None for name in required):
            kept.append(i)
    y = np.array([encoded[outcome][i] for i in kept], dtype=float)
    x_cols = [np.ones(len(kept))]
    names = ["Intercept"]
    for name in predictors:
        x_cols.append(np.array([encoded[name][i] for i in kept], dtype=float))
        names.append(name)
    if len(kept) == 0:
        return AnalysisResult(
            experiment_id=plan_payload["experiment_id"],
            hypothesis_id=plan_payload["hypothesis_id"],
            model_formula=plan_payload["model_formula"],
            n_total=len(rows),
            n_used=0,
            warnings=["no_complete_cases"],
            status="failed",
        )
    x = np.column_stack(x_cols)
    beta = np.linalg.pinv(x) @ y
    fitted = x @ beta
    resid = y - fitted
    df = len(y) - x.shape[1]
    if df <= 0:
        warnings.append("nonpositive_degrees_of_freedom")
    sigma2 = float((resid @ resid) / max(1, df))
    cov = sigma2 * np.linalg.pinv(x.T @ x)
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    p_values: dict[str, float] = {}
    coefficients: dict[str, float] = {}
    ci: dict[str, list[float]] = {}
    effects: dict[str, float] = {}
    for idx, name in enumerate(names):
        coefficients[name] = round(float(beta[idx]), 6)
        stat = abs(float(beta[idx] / se[idx])) if se[idx] > 0 else 0.0
        p_values[name] = round(float(math.erfc(stat / math.sqrt(2))), 6)
        ci[name] = [round(float(beta[idx] - 1.96 * se[idx]), 6), round(float(beta[idx] + 1.96 * se[idx]), 6)]
        if name != "Intercept":
            sx = float(np.std(x[:, idx])) or 1.0
            sy = float(np.std(y)) or 1.0
            effects[name] = round(float(beta[idx] * sx / sy), 6)
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) @ (y - y.mean()))) if len(y) else 0.0
    result = AnalysisResult(
        experiment_id=plan_payload["experiment_id"],
        hypothesis_id=plan_payload["hypothesis_id"],
        model_formula=plan_payload["model_formula"],
        n_total=len(rows),
        n_used=len(kept),
        coefficients=coefficients,
        p_values=p_values,
        corrected_p_values=_bh({k: v for k, v in p_values.items() if k != "Intercept"}),
        effect_sizes=effects,
        confidence_intervals=ci,
        model_fit={"r_squared": round(1.0 - ss_res / ss_tot, 6) if ss_tot else 0.0},
        warnings=warnings,
        status="ok",
    )
    return result


def run_stats_agent(config: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(config["_project_root"])
    outputs = config.get("outputs", {})
    locked_dir = resolve_path(outputs["locked_plans_dir"], root)
    results_dir = resolve_path(outputs["results_dir"], root)
    results_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sorted(locked_dir.glob("*_locked_plan.json")):
        plan = read_json(path)
        if plan.get("lock_status") != "locked":
            continue
        result = run_locked_plan(plan, config)
        payload = result.model_dump(mode="json")
        write_json(results_dir / f"{result.experiment_id}_result.json", payload)
        write_csv(results_dir / f"{result.experiment_id}_result.csv", [{"term": k, "coefficient": v, "p_value": result.p_values.get(k, ""), "corrected_p_value": result.corrected_p_values.get(k, ""), "effect_size": result.effect_sizes.get(k, "")} for k, v in result.coefficients.items()])
        results.append(payload)
    return results
