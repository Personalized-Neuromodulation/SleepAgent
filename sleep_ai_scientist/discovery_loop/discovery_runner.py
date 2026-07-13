from __future__ import annotations

import shutil
from pathlib import Path
from statistics import mean
from typing import Any

from sleep_ai_scientist.common.config import load_config, resolve_path
from sleep_ai_scientist.common.io import read_json, read_yaml, write_json
from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline


def run_discovery_loop(config_path_value: str | Path = "configs/discovery_loop_config.yaml") -> dict[str, Any]:
    config_path = resolve_path(config_path_value)
    config = load_config(config_path)
    loop_cfg = config.get("discovery_loop", {})
    paths = config.get("paths", {})
    max_iterations = int(loop_cfg.get("max_iterations", 3))
    verbose = bool(loop_cfg.get("verbose", True))

    hypothesis_config_path = resolve_path(config.get("hypothesis", {}).get("config_path", "configs/hypothesis_config.yaml"))
    experiment_config_path = resolve_path(config.get("experiment", {}).get("config_path", "configs/experiment_config.yaml"))
    output_dir = resolve_path(paths.get("loop_output_dir", "outputs/discovery_loop"))
    state_path = resolve_path(paths.get("iteration_state", output_dir / "loop_state.json"))
    report_path = resolve_path(paths.get("iteration_report", "reports/discovery_loop_report.md"))
    output_dir.mkdir(parents=True, exist_ok=True)

    previous_hypothesis_ids: set[str] = set()
    reward_history: list[float] = []
    iterations: list[dict[str, Any]] = []
    stop_reason = "max_iterations"

    _log(verbose, f"start config={config_path} max_iterations={max_iterations}")
    _log(verbose, f"hypothesis_config={hypothesis_config_path}")
    _log(verbose, f"experiment_config={experiment_config_path}")

    for iteration in range(1, max_iterations + 1):
        iteration_id = f"iteration_{iteration:03d}"
        iteration_dir = output_dir / iteration_id
        iteration_dir.mkdir(parents=True, exist_ok=True)
        _log(verbose, f"{iteration_id} hypothesis start")
        hypothesis_summary = run_hypothesis_pipeline(hypothesis_config_path)
        _log(verbose, f"{iteration_id} hypothesis done hypotheses={hypothesis_summary.get('hypotheses')}")

        _log(verbose, f"{iteration_id} experiment start")
        experiment_summary = run_experiment_pipeline(experiment_config_path)
        _log(verbose, f"{iteration_id} experiment done plans={experiment_summary.get('plans')}")

        metrics = _collect_iteration_metrics(
            iteration=iteration,
            hypothesis_config_path=hypothesis_config_path,
            experiment_config_path=experiment_config_path,
            previous_hypothesis_ids=previous_hypothesis_ids,
        )
        current_ids = set(metrics.get("hypothesis_ids", []))
        previous_hypothesis_ids = current_ids
        reward_mean = metrics.get("reward_mean")
        if reward_mean is not None:
            reward_history.append(float(reward_mean))
        snapshot = _snapshot_iteration(
            iteration_dir,
            hypothesis_config_path=hypothesis_config_path,
            experiment_config_path=experiment_config_path,
            snapshot_features=bool(loop_cfg.get("snapshot_features", True)),
        )
        record = {
            "iteration": iteration,
            "iteration_id": iteration_id,
            "hypothesis_summary": hypothesis_summary,
            "experiment_summary": experiment_summary,
            "metrics": metrics,
            "snapshot": snapshot,
        }
        iterations.append(record)
        write_json(iteration_dir / "loop_summary.json", record)
        write_json(state_path, {"config": str(config_path), "iterations": iterations, "stop_reason": stop_reason})

        stop_reason = _stop_reason(config, metrics, reward_history, iteration)
        _log(verbose, f"{iteration_id} metrics active={metrics.get('active_hypotheses')} feedback={metrics.get('feedback_records')} reward_mean={metrics.get('reward_mean')}")
        if stop_reason:
            _log(verbose, f"{iteration_id} stop reason={stop_reason}")
            break
        stop_reason = "max_iterations"

    result = {
        "run_id": str(loop_cfg.get("run_id", "sleep_discovery_loop")),
        "iterations": len(iterations),
        "stop_reason": stop_reason,
        "loop_output_dir": str(output_dir),
        "iteration_state": str(state_path),
        "iteration_report": str(report_path),
    }
    write_json(state_path, {"config": str(config_path), "result": result, "iterations": iterations})
    _write_report(report_path, result, iterations)
    _log(verbose, f"done iterations={result['iterations']} stop_reason={stop_reason}")
    return result


def _collect_iteration_metrics(
    *,
    iteration: int,
    hypothesis_config_path: Path,
    experiment_config_path: Path,
    previous_hypothesis_ids: set[str],
) -> dict[str, Any]:
    hypothesis_config = read_yaml(hypothesis_config_path)
    experiment_config = read_yaml(experiment_config_path)
    hypothesis_output_dir = resolve_path(hypothesis_config.get("paths", {}).get("output_hypotheses_dir", "outputs/hypotheses"))
    hypothesis_pool_path = hypothesis_output_dir / "hypothesis_pool.json"
    top_k_path = hypothesis_output_dir / "top_k_hypotheses.json"
    feedback_path = resolve_path(experiment_config.get("paths", {}).get("experimental_feedback", "outputs/hypotheses/experimental_feedback.json"))
    experiment_results_path = resolve_path(experiment_config.get("paths", {}).get("experiment_results", "outputs/experiments/experiment_results.json"))

    hypotheses = _read_json_list(hypothesis_pool_path)
    hypothesis_ids = [str(item.get("hypothesis_id", "")) for item in hypotheses if isinstance(item, dict)]
    statuses: dict[str, int] = {}
    for item in hypotheses:
        status = str(item.get("status", "unknown")) if isinstance(item, dict) else "unknown"
        statuses[status] = statuses.get(status, 0) + 1
    top_k = _read_json_list(top_k_path)
    feedback = _read_json_list(feedback_path)
    rewards = [_as_float(item.get("computed_reward")) for item in feedback if isinstance(item, dict)]
    rewards = [item for item in rewards if item is not None]
    experiment_results = _read_json_list(experiment_results_path)
    return {
        "iteration": iteration,
        "hypothesis_pool_path": str(hypothesis_pool_path),
        "experiment_results_path": str(experiment_results_path),
        "experimental_feedback_path": str(feedback_path),
        "hypothesis_count": len(hypotheses),
        "hypothesis_ids": hypothesis_ids,
        "new_hypotheses": len(set(hypothesis_ids) - previous_hypothesis_ids) if previous_hypothesis_ids else len(hypothesis_ids),
        "status_counts": statuses,
        "active_hypotheses": statuses.get("active", 0),
        "top_k_count": len(top_k),
        "experiment_result_count": len(experiment_results),
        "feedback_records": len(feedback),
        "validated_feedback": sum(1 for item in rewards if item > 0.3),
        "refuted_feedback": sum(1 for item in rewards if item < -0.3),
        "reward_mean": round(mean(rewards), 6) if rewards else None,
    }


def _snapshot_iteration(
    iteration_dir: Path,
    *,
    hypothesis_config_path: Path,
    experiment_config_path: Path,
    snapshot_features: bool,
) -> dict[str, Any]:
    hypothesis_config = read_yaml(hypothesis_config_path)
    experiment_config = read_yaml(experiment_config_path)
    copied: dict[str, str] = {}

    hypothesis_output_dir = resolve_path(hypothesis_config.get("paths", {}).get("output_hypotheses_dir", "outputs/hypotheses"))
    _copy_path(hypothesis_output_dir, iteration_dir / "hypothesis", copied, "hypothesis")
    hypothesis_report = hypothesis_config.get("paths", {}).get("report_path")
    if hypothesis_report:
        _copy_path(resolve_path(hypothesis_report), iteration_dir / "hypothesis_report.md", copied, "hypothesis_report")

    experiment_paths = experiment_config.get("paths", {})
    for key, default in {
        "experiment_results": "outputs/experiments/experiment_results.json",
        "experimental_feedback": "outputs/hypotheses/experimental_feedback.json",
        "experiment_report": "reports/phase3_experiment_report.md",
    }.items():
        _copy_path(resolve_path(experiment_paths.get(key, default)), iteration_dir / "experiment" / Path(experiment_paths.get(key, default)).name, copied, key)

    if snapshot_features:
        feature_root = experiment_config.get("feature_extraction", {}).get("output_root")
        if feature_root:
            _copy_path(resolve_path(feature_root), iteration_dir / "features", copied, "features")
    return copied


def _copy_path(source: Path, target: Path, copied: dict[str, str], label: str) -> None:
    if not source.exists():
        return
    if source.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    copied[label] = str(target)


def _stop_reason(config: dict[str, Any], metrics: dict[str, Any], reward_history: list[float], iteration: int) -> str:
    stop_cfg = config.get("discovery_loop", {}).get("stop_conditions", {})
    if bool(stop_cfg.get("no_active_hypotheses", True)) and int(metrics.get("active_hypotheses", 0)) == 0:
        return "no_active_hypotheses"
    if bool(stop_cfg.get("no_experimental_feedback", False)) and int(metrics.get("feedback_records", 0)) == 0:
        return "no_experimental_feedback"
    convergence = stop_cfg.get("reward_convergence", {})
    if bool(convergence.get("enabled", True)):
        min_iterations = int(convergence.get("min_iterations", 2))
        delta = float(convergence.get("delta", 0.03))
        if iteration >= min_iterations and len(reward_history) >= 2 and abs(reward_history[-1] - reward_history[-2]) <= delta:
            return "reward_converged"
    return ""


def _write_report(path: Path, result: dict[str, Any], iterations: list[dict[str, Any]]) -> None:
    lines = [
        "# Discovery Loop Report",
        "",
        f"- run_id: `{result['run_id']}`",
        f"- iterations: {result['iterations']}",
        f"- stop_reason: `{result['stop_reason']}`",
        "",
    ]
    for record in iterations:
        metrics = record.get("metrics", {})
        lines.extend(
            [
                f"## {record.get('iteration_id')}",
                f"- hypotheses: {metrics.get('hypothesis_count')}",
                f"- active_hypotheses: {metrics.get('active_hypotheses')}",
                f"- new_hypotheses: {metrics.get('new_hypotheses')}",
                f"- experiment_results: {metrics.get('experiment_result_count')}",
                f"- feedback_records: {metrics.get('feedback_records')}",
                f"- reward_mean: {metrics.get('reward_mean')}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _read_json_list(path: Path) -> list[Any]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    payload = read_json(path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("hypotheses", "feedback", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _log(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[discovery_loop] {message}", flush=True)


if __name__ == "__main__":
    print(run_discovery_loop())
