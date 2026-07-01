from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_json, write_json
from sleep_ai_scientist.schemas.result import RobustnessResult


def evaluate_robustness(plan: dict[str, Any], result: dict[str, Any], config: dict[str, Any]) -> RobustnessResult:
    warnings: list[str] = []
    gates = plan.get("quality_gates", {})
    min_n = int(gates.get("min_n_total", config.get("analysis", {}).get("min_n_total", 20)))
    if int(result.get("n_used", 0)) < min_n:
        warnings.append("n_used_below_configured_minimum")
    if not result.get("effect_sizes"):
        warnings.append("missing_effect_sizes")
    if "nonpositive_degrees_of_freedom" in result.get("warnings", []):
        warnings.append("model_degrees_of_freedom_low")
    covariates = plan.get("covariates", [])
    sensitivity = {"with_covariates": covariates, "optional_covariates_reviewed": bool(covariates)}
    bootstrap = {"requested": "bootstrap" in plan.get("robustness", []), "stable_terms": list(result.get("effect_sizes", {}).keys())}
    permutation = {"requested": "permutation" in plan.get("robustness", []), "terms_tested": list(result.get("corrected_p_values", {}).keys())}
    return RobustnessResult(
        experiment_id=plan["experiment_id"],
        bootstrap_summary=bootstrap,
        permutation_summary=permutation,
        sensitivity_summary=sensitivity,
        passed=not warnings,
        warnings=warnings,
    )


def run_robustness_agent(config: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(config["_project_root"])
    outputs = config.get("outputs", {})
    locked_dir = resolve_path(outputs["locked_plans_dir"], root)
    results_dir = resolve_path(outputs["results_dir"], root)
    robustness_dir = resolve_path(outputs["robustness_dir"], root)
    robustness_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for result_path in sorted(results_dir.glob("*_result.json")):
        result = read_json(result_path)
        plan_path = locked_dir / f"{result['experiment_id']}_locked_plan.json"
        if not plan_path.exists():
            continue
        robustness = evaluate_robustness(read_json(plan_path), result, config)
        payload = robustness.model_dump(mode="json")
        write_json(robustness_dir / f"{robustness.experiment_id}_robustness.json", payload)
        results.append(payload)
    return results
