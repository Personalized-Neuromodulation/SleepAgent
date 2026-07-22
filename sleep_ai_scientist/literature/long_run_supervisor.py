from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.common.io import read_json, write_json
from sleep_ai_scientist.literature.checkpoint import load_checkpoint, write_checkpoint
from sleep_ai_scientist.literature.error_recovery import write_error_bundle
from sleep_ai_scientist.literature.iterative_builder import run_iteration
from sleep_ai_scientist.literature.status_report import write_status_report


def _run_dir(root: Path, run_name: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / "outputs/literature/long_runs" / f"run_{timestamp}_{run_name}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_long_run(
    config_path_value: str | Path = "configs/literature_long_run_config.yaml",
    *,
    max_runtime_hours: float | None = None,
    resume: str | Path | None = None,
    dry_run: bool = False,
    backend: str | None = "sqlite",
) -> dict[str, Any]:
    config = load_config(config_path_value)
    root = Path(config["_project_root"])
    run_name = config.get("project", {}).get("run_name", "sleep_library_long_run")
    if resume:
        checkpoint = load_checkpoint(resume)
        run_dir = Path(checkpoint.get("run_dir", Path(resume).parents[1]))
        start_iteration = int(checkpoint.get("iteration") or 0) + 1
        run_id = checkpoint.get("run_id", run_dir.name)
    else:
        run_dir = _run_dir(root, run_name)
        start_iteration = 1
        run_id = run_dir.name
    runtime = config.get("runtime", {})
    requested_hours = max_runtime_hours if max_runtime_hours is not None else float(runtime.get("max_runtime_hours", 10))
    max_iterations = 1 if dry_run else max(1, min(int(runtime.get("max_iterations", 20)), int(requested_hours * 4) or 1))
    summaries = []
    latest_checkpoint = None
    errors: list[str] = []
    for offset in range(max_iterations):
        iteration = start_iteration + offset
        stage = "iteration"
        try:
            summary = run_iteration(config, iteration, run_dir, dry_run=dry_run, backend=backend)
            summaries.append(summary)
            latest_checkpoint = write_checkpoint(
                run_dir,
                {
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "status": "dry_run" if dry_run else "running",
                    "last_successful_stage": stage,
                    "summary": summary,
                },
                iteration=iteration,
            )
            write_status_report(
                run_dir,
                iteration,
                {
                    "run_id": run_id,
                    "elapsed_time": f"iteration_{iteration}",
                    "current_iteration": iteration,
                    "current_stage": stage,
                    "total_records": summary.get("registry_records", 0),
                    "new_records_this_hour": summary.get("api_papers", 0),
                    "duplicate_rate": summary.get("duplicate_groups", 0),
                    "coverage_summary": summary.get("coverage", {}),
                    "provider_health": summary.get("provider_summary", {}),
                    "sparse_query_groups": summary.get("sparse_query_groups", []),
                    "last_checkpoint": str(latest_checkpoint),
                    "warnings": summary.get("warnings", []),
                    "errors": errors,
                    "next_planned_iteration": iteration + 1,
                },
            )
        except Exception as exc:
            errors.append(str(exc))
            bundle = write_error_bundle(run_dir, exc, stage, config=config, latest_checkpoint=read_json(latest_checkpoint) if latest_checkpoint and Path(latest_checkpoint).exists() else {})
            latest_checkpoint = write_checkpoint(run_dir, {"run_id": run_id, "run_dir": str(run_dir), "status": "error", "failed_stage": stage, "error_bundle_path": str(bundle)}, iteration=iteration)
            if not config.get("error_recovery", {}).get("continue_on_provider_failure", True):
                break
    final = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "dry_run": dry_run,
        "max_runtime_hours": requested_hours,
        "iterations_completed": len(summaries),
        "latest_checkpoint": str(latest_checkpoint) if latest_checkpoint else "",
        "errors": errors,
        "summaries": summaries,
    }
    write_json(run_dir / "final_status.json", final)
    return final

