from __future__ import annotations

import shutil
from pathlib import Path
from statistics import mean
from typing import Any

from sleep_ai_scientist.common.config import load_config, resolve_path
from sleep_ai_scientist.common.io import read_json, read_yaml, write_json, write_yaml
from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline
from sleep_ai_scientist.foundation.foundation_pipeline import run_foundation_pipeline
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline
from sleep_ai_scientist.literature.experiment_intent import (
    append_queries_to_config,
    build_literature_expansion_plan,
    write_intent_records,
)
from sleep_ai_scientist.literature.library_builder import run_literature_build


def run_discovery_loop(config_path_value: str | Path = "configs/discovery_loop_config.yaml") -> dict[str, Any]:
    config_path = resolve_path(config_path_value)
    config = load_config(config_path)
    loop_cfg = config.get("discovery_loop", {})
    paths = config.get("paths", {})
    max_iterations = int(loop_cfg.get("max_iterations", 3))
    verbose = bool(loop_cfg.get("verbose", True))
    enable_foundation_grounding_refresh = bool(loop_cfg.get("enable_foundation_grounding_refresh", False))

    hypothesis_config_path = resolve_path(config.get("hypothesis", {}).get("config_path", "configs/hypothesis_config.yaml"))
    experiment_config_path = resolve_path(config.get("experiment", {}).get("config_path", "configs/experiment_config.yaml"))
    foundation_config_path = resolve_path(config.get("foundation", {}).get("config_path", "configs/foundation_config.yaml"))
    grounding_config_path = resolve_path(config.get("grounding", {}).get("config_path", "configs/grounding_config.yaml"))
    output_dir = resolve_path(paths.get("loop_output_dir", "outputs/discovery_loop"))
    state_path = resolve_path(paths.get("iteration_state", output_dir / "loop_state.json"))
    report_path = resolve_path(paths.get("iteration_report", "reports/phase4_discovery_loop_report.md"))
    output_dir.mkdir(parents=True, exist_ok=True)

    previous_hypothesis_ids: set[str] = set()
    reward_history: list[float] = []
    iterations: list[dict[str, Any]] = []
    stop_reason = "max_iterations"

    _log(verbose, f"start config={config_path} max_iterations={max_iterations}")
    _log(verbose, f"hypothesis_config={hypothesis_config_path}")
    _log(verbose, f"experiment_config={experiment_config_path}")
    _log(verbose, f"foundation_config={foundation_config_path}")
    _log(verbose, f"grounding_config={grounding_config_path}")

    for iteration in range(1, max_iterations + 1):
        iteration_id = f"iteration_{iteration:03d}"
        iteration_dir = output_dir / iteration_id
        iteration_dir.mkdir(parents=True, exist_ok=True)
        hypothesis_feedback_input = _hypothesis_feedback_input(hypothesis_config_path)
        _log(verbose, f"{iteration_id} hypothesis start")
        hypothesis_summary = run_hypothesis_pipeline(hypothesis_config_path)
        _log(verbose, f"{iteration_id} hypothesis done hypotheses={hypothesis_summary.get('hypotheses')}")

        _log(verbose, f"{iteration_id} experiment start")
        experiment_summary = run_experiment_pipeline(experiment_config_path)
        _log(verbose, f"{iteration_id} experiment done plans={experiment_summary.get('plans')}")

        if enable_foundation_grounding_refresh:
            foundation_update = _update_foundation_from_experiment_features(
                experiment_summary,
                foundation_config_path=foundation_config_path,
                iteration_dir=iteration_dir,
                iteration_id=iteration_id,
                verbose=verbose,
            )
            literature_expansion = _build_literature_expansion_if_needed(
                experiment_summary,
                foundation_update=foundation_update,
                literature_cfg=config.get("literature", {}),
                iteration_dir=iteration_dir,
                iteration_id=iteration_id,
                verbose=verbose,
            )
            literature_refresh = _refresh_literature_if_needed(
                literature_expansion,
                literature_cfg=config.get("literature", {}),
                iteration_dir=iteration_dir,
                verbose=verbose,
            )
            grounding_refresh = _refresh_grounding_if_needed(
                foundation_update,
                grounding_config_path=grounding_config_path,
                grounding_cfg=config.get("grounding", {}),
                verbose=verbose,
            )
        else:
            foundation_update = {"foundation_changed": False, "reason": "foundation_grounding_refresh_disabled"}
            literature_expansion = {"accepted_query_count": 0, "reason": "foundation_grounding_refresh_disabled"}
            literature_refresh = {"refreshed": False, "reason": "foundation_grounding_refresh_disabled"}
            grounding_refresh = {"refreshed": False, "reason": "foundation_grounding_refresh_disabled"}

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
            "hypothesis_feedback_input": hypothesis_feedback_input,
            "hypothesis_summary": hypothesis_summary,
            "experiment_summary": experiment_summary,
            "foundation_update": foundation_update,
            "literature_expansion": literature_expansion,
            "literature_refresh": literature_refresh,
            "grounding_refresh": grounding_refresh,
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
        "foundation_changed": any(bool(item.get("foundation_update", {}).get("foundation_changed")) for item in iterations),
        "grounding_refreshes": sum(1 for item in iterations if bool(item.get("grounding_refresh", {}).get("refreshed"))),
        "last_experiment_feedback": _last_experiment_feedback(iterations),
        "hypothesis_feedback_available": any(bool(item.get("hypothesis_feedback_input", {}).get("available")) for item in iterations),
        "loop_output_dir": str(output_dir),
        "iteration_state": str(state_path),
        "iteration_report": str(report_path),
    }
    write_json(state_path, {"config": str(config_path), "result": result, "iterations": iterations})
    _write_report(report_path, result, iterations)
    _log(verbose, f"done iterations={result['iterations']} stop_reason={stop_reason}")
    return result


def _hypothesis_feedback_input(hypothesis_config_path: Path) -> dict[str, Any]:
    hypothesis_config = read_yaml(hypothesis_config_path)
    feedback_path = resolve_path(hypothesis_config.get("paths", {}).get("experimental_feedback", "outputs/hypotheses/experimental_feedback.json"))
    exists = feedback_path.exists() and feedback_path.is_file() and feedback_path.stat().st_size > 0
    return {
        "path": str(feedback_path),
        "available": exists,
        "size": feedback_path.stat().st_size if exists else 0,
    }


MODALITY_INPUT_KEYS = {
    "eeg": "eeg_features",
    "fmri": "fmri_features",
    "dti": "dti_features",
    "mri": "mri_features",
    "scale": "scale_features",
    "scales": "scale_features",
}


def _update_foundation_from_experiment_features(
    experiment_summary: dict[str, Any],
    *,
    foundation_config_path: Path,
    iteration_dir: Path,
    iteration_id: str,
    verbose: bool,
) -> dict[str, Any]:
    feature_tables = _valid_feature_tables(experiment_summary.get("feature_tables", []))
    if not feature_tables:
        return {"foundation_changed": False, "reason": "no_feature_tables"}

    base_config = read_yaml(foundation_config_path)
    update_config = dict(base_config)
    update_config.pop("_config_path", None)
    update_config.pop("_project_root", None)
    update_config.pop("foundation", None)
    update_config.setdefault("runtime", {})["allow_fixtures"] = False
    inputs = {
        "subject_table": str(feature_tables[0]["path"]),
        "eeg_features": "__sleepagent_missing_eeg_features__.csv",
        "fmri_features": "__sleepagent_missing_fmri_features__.csv",
        "dti_features": "__sleepagent_missing_dti_features__.csv",
        "mri_features": "__sleepagent_missing_mri_features__.csv",
        "scale_features": "__sleepagent_missing_scale_features__.csv",
        "qc_summary": "__sleepagent_missing_qc_summary__.csv",
    }
    for table in feature_tables:
        key = _feature_table_input_key(table.get("modality", ""))
        if key:
            inputs[key] = str(table["path"])
    update_config["inputs"] = inputs
    update_config["data_assets"] = {
        "source": "experiment",
        "iteration_id": iteration_id,
        "feature_tables": feature_tables,
        "experiment_summary": {
            key: experiment_summary.get(key)
            for key in ["plans", "results", "experiment_results", "experimental_feedback"]
            if experiment_summary.get(key) is not None
        },
    }
    config_path = iteration_dir / "foundation_update_config.yaml"
    write_yaml(config_path, update_config)
    summary = run_foundation_pipeline(config_path)
    data_assets = summary.get("data_assets", {})
    _log(verbose, f"{iteration_dir.name} foundation updated features={summary.get('feature_count')} assets={data_assets.get('asset_count', 0)}")
    return {
        "foundation_changed": True,
        "reason": "experiment_feature_tables",
        "feature_tables": feature_tables,
        "foundation_config": str(config_path),
        "foundation_summary": summary,
        "data_asset_registry": data_assets.get("registry", ""),
        "update_history": data_assets.get("update_history", ""),
        "data_asset_count": data_assets.get("asset_count", 0),
    }


def _valid_feature_tables(raw_tables: Any) -> list[dict[str, str]]:
    if not isinstance(raw_tables, list):
        return []
    tables: list[dict[str, str]] = []
    for item in raw_tables:
        if not isinstance(item, dict):
            continue
        path = resolve_path(item.get("path", ""))
        if not path.exists() or not path.is_file() or path.stat().st_size == 0:
            continue
        tables.append({"modality": str(item.get("modality", "")), "path": str(path)})
    return tables


def _feature_table_input_key(modality: str) -> str:
    normalized = str(modality).strip().lower()
    return MODALITY_INPUT_KEYS.get(normalized, "")


def _refresh_grounding_if_needed(
    foundation_update: dict[str, Any],
    *,
    grounding_config_path: Path,
    grounding_cfg: dict[str, Any],
    verbose: bool,
) -> dict[str, Any]:
    if not foundation_update.get("foundation_changed"):
        return {"refreshed": False, "reason": "foundation_unchanged"}
    corpus_version = str(grounding_cfg.get("corpus_version", "sleepagent_grounding_data_constrained_v1"))
    summary = run_grounding_pipeline(grounding_config_path, corpus_version=corpus_version)
    _log(verbose, f"grounding refreshed corpus_version={corpus_version}")
    return {
        "refreshed": True,
        "reason": "foundation_changed",
        "grounding_config": str(grounding_config_path),
        "corpus_version": corpus_version,
        "grounding_summary": summary,
    }


def _build_literature_expansion_if_needed(
    experiment_summary: dict[str, Any],
    foundation_update: dict[str, Any],
    *,
    literature_cfg: dict[str, Any],
    iteration_dir: Path,
    iteration_id: str,
    verbose: bool,
) -> dict[str, Any]:
    if not foundation_update.get("foundation_changed"):
        return {"accepted_query_count": 0, "reason": "foundation_unchanged"}
    if not bool(literature_cfg.get("enabled", False)):
        return {"accepted_query_count": 0, "reason": "literature_refresh_disabled"}
    query_config_path = resolve_path(literature_cfg.get("query_config_path", "configs/literature_queries.yaml"))
    enriched = _experiment_summary_for_literature_intent(experiment_summary)
    _log(verbose, f"[literature_intent] start iteration={iteration_id}")
    plan = build_literature_expansion_plan(enriched, iteration_id, query_config_path)
    signals = plan.get("signals", {})
    _log(
        verbose,
        "[literature_intent] extracted signals "
        f"failed_tests={signals.get('failed_tests', 0)} negative_control_failures={signals.get('negative_control_failures', 0)} "
        f"missing_variables={signals.get('missing_variables', 0)} modality_gaps={signals.get('modality_gaps', 0)}",
    )
    _log(verbose, f"[literature_intent] candidates generated={plan.get('candidate_count', 0)}")
    _log(
        verbose,
        f"[literature_intent] accepted={plan.get('accepted_query_count', 0)} "
        f"rejected_duplicate={plan.get('rejected_duplicate_count', 0)} rejected_invalid={plan.get('rejected_invalid_count', 0)}",
    )
    append_summary = {"appended": 0, "group": "experiment_feedback_expansion", "query_config": str(query_config_path)}
    accepted = plan.get("accepted_queries", [])
    if accepted:
        append_summary = append_queries_to_config(query_config_path, accepted)
        write_intent_records(resolve_path(literature_cfg.get("intent_log_path", "outputs/literature/query_expansion_intents.jsonl")), accepted)
    _log(
        verbose,
        f"[literature_intent] appended query_config={append_summary.get('query_config')} "
        f"group={append_summary.get('group')} count={append_summary.get('appended')}",
    )
    incremental_query_config = ""
    if accepted:
        incremental_query_config = str(_write_incremental_query_config(query_config_path, accepted, iteration_dir))
    plan_path = iteration_dir / "literature_expansion_plan.json"
    payload = {**plan, "append_summary": append_summary, "incremental_query_config": incremental_query_config}
    write_json(plan_path, payload)
    return payload


def _refresh_literature_if_needed(
    literature_expansion: dict[str, Any],
    *,
    literature_cfg: dict[str, Any],
    iteration_dir: Path,
    verbose: bool,
) -> dict[str, Any]:
    accepted_count = int(literature_expansion.get("accepted_query_count", 0) or 0)
    if accepted_count <= 0:
        _log(verbose, "[literature_refresh] skipped reason=no_new_experiment_queries")
        return {"refreshed": False, "reason": "no_new_experiment_queries", "accepted_query_count": 0}
    if not bool(literature_cfg.get("enabled", False)):
        return {"refreshed": False, "reason": "literature_refresh_disabled", "accepted_query_count": accepted_count}
    config_path = resolve_path(literature_cfg.get("config_path", "configs/literature_library_config.yaml"))
    query_config_path = resolve_path(literature_expansion.get("incremental_query_config") or literature_cfg.get("query_config_path", "configs/literature_queries.yaml"))
    library_version = literature_cfg.get("library_version")
    _log(verbose, f"[literature_refresh] incremental start new_queries={accepted_count} query_config={query_config_path}")
    summary = run_literature_build(
        config_path,
        query_config_path=query_config_path,
        library_version=str(library_version) if library_version else None,
        enable_rag_index=True,
    )
    rag_index = summary.get("rag_index") or {}
    embedding = rag_index.get("embedding") if isinstance(rag_index, dict) else {}
    _log(
        verbose,
        "literature DB refreshed registry_records="
        f"{summary.get('registry_records')} rag_chunks={rag_index.get('chunk_count') if isinstance(rag_index, dict) else 0} "
        f"embedding_vectors={embedding.get('vector_count') if isinstance(embedding, dict) else 0}",
    )
    return {
        "refreshed": True,
        "reason": "new_experiment_queries",
        "accepted_query_count": accepted_count,
        "literature_config": str(config_path),
        "query_config": str(query_config_path),
        "library_version": str(library_version or summary.get("library_version", "")),
        "literature_summary": summary,
    }


def _experiment_summary_for_literature_intent(experiment_summary: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(experiment_summary)
    results_path = experiment_summary.get("results") or experiment_summary.get("experiment_results")
    feedback_path = experiment_summary.get("experimental_feedback")
    if isinstance(results_path, str):
        path = resolve_path(results_path)
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            enriched["results_payload"] = _read_json_list(path)
    if isinstance(feedback_path, str):
        path = resolve_path(feedback_path)
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            enriched["feedback_payload"] = _read_json_list(path)
    return enriched


def _write_incremental_query_config(query_config_path: Path, accepted_queries: list[dict[str, Any]], iteration_dir: Path) -> Path:
    base = read_yaml(query_config_path) if query_config_path.exists() else {}
    library = base.get("query_sets", {}).get("library", {}) if isinstance(base, dict) else {}
    settings = dict(library.get("settings", {})) if isinstance(library, dict) else {}
    query_set = dict(library.get("query_set", {})) if isinstance(library, dict) else {}
    query_set["version"] = f"{query_set.get('version', 'experiment_feedback')}_incremental"
    payload = {
        "query_file": {
            "version": "sleepagent_experiment_feedback_incremental",
            "description": "Incremental query set generated from experiment feedback for one discovery iteration.",
        },
        "query_sets": {
            "library": {
                "query_set": query_set,
                "settings": settings,
                "queries": {
                    "experiment_feedback_expansion": [str(item.get("query", "")).strip() for item in accepted_queries if str(item.get("query", "")).strip()]
                },
            }
        },
    }
    path = iteration_dir / "literature_incremental_queries.yaml"
    write_yaml(path, payload)
    return path


def _last_experiment_feedback(iterations: list[dict[str, Any]]) -> str:
    for record in reversed(iterations):
        value = record.get("experiment_summary", {}).get("experimental_feedback")
        if value:
            return str(value)
        value = record.get("metrics", {}).get("experimental_feedback_path")
        if value:
            return str(value)
    return ""


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
    validated = sum(1 for item in feedback if isinstance(item, dict) and bool(item.get("validated", False)))
    refuted = sum(1 for item in feedback if isinstance(item, dict) and bool(item.get("refuted", False)))
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
        "validated_feedback": validated,
        "refuted_feedback": refuted,
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
                f"- hypothesis_feedback_input: {record.get('hypothesis_feedback_input', {}).get('available')}",
                f"- foundation_changed: {record.get('foundation_update', {}).get('foundation_changed')}",
                f"- grounding_refreshed: {record.get('grounding_refresh', {}).get('refreshed')}",
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
