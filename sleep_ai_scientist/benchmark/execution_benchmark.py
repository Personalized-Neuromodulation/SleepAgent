from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.benchmark.utils import as_int, input_path, model_dump_rows, output_path
from sleep_ai_scientist.common.io import read_json, write_csv
from sleep_ai_scientist.schemas.benchmark import ExecutionBenchmarkScore


def _json(path: Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else {}


def run_execution_benchmark(config: dict[str, Any]) -> list[ExecutionBenchmarkScore]:
    locked_dir = input_path(config, "locked_plans_dir")
    results_dir = input_path(config, "results_dir")
    robustness_dir = input_path(config, "robustness_dir")
    critic_dir = input_path(config, "critic_reviews_dir")
    scores = []
    plan_paths = sorted(locked_dir.glob("*_locked_plan.json")) if locked_dir.exists() else []
    for plan_path in plan_paths:
        plan = _json(plan_path)
        exp_id = plan.get("experiment_id", plan_path.name.replace("_locked_plan.json", ""))
        result_path = results_dir / f"{exp_id}_result.json"
        robustness_path = robustness_dir / f"{exp_id}_robustness.json"
        critic_path = critic_dir / f"{exp_id}_critic_review.json"
        result = _json(result_path)
        n_used = as_int(result.get("n_used"), 0) if result else None
        min_n = as_int(plan.get("quality_gates", {}).get("min_n_total"), 20)
        warnings = []
        if plan.get("lock_status") != "locked":
            warnings.append("plan_not_locked")
        if not result_path.exists():
            warnings.append("missing_result_file")
        if n_used is not None and n_used < min_n:
            warnings.append("n_used_below_gate")
        checks = [plan_path.exists(), plan.get("lock_status") == "locked", result_path.exists(), robustness_path.exists(), critic_path.exists()]
        score = round(sum(1 for item in checks if item) / len(checks), 4)
        scores.append(
            ExecutionBenchmarkScore(
                experiment_id=exp_id,
                hypothesis_id=plan.get("hypothesis_id", ""),
                has_locked_plan=plan.get("lock_status") == "locked",
                plan_file_exists=plan_path.exists(),
                result_file_exists=result_path.exists(),
                robustness_file_exists=robustness_path.exists(),
                critic_review_exists=critic_path.exists(),
                n_used=n_used,
                model_formula=result.get("model_formula") or plan.get("model_formula"),
                execution_success=result_path.exists() and result.get("status") == "ok" and plan.get("lock_status") == "locked",
                execution_score=score,
                warnings=warnings,
            )
        )
    write_csv(output_path(config, "execution_benchmark_scores"), model_dump_rows(scores))
    return scores
