from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_csv, read_json, write_json
from sleep_ai_scientist.experiment.experiment_dsl import hypothesis_to_plan
from sleep_ai_scientist.schemas.experiment import ExperimentPlanStatus
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, HypothesisVariables


def _hypothesis(payload: dict[str, Any]) -> HypothesisRecord:
    if isinstance(payload.get("variables"), dict):
        payload = dict(payload)
        payload["variables"] = HypothesisVariables(**payload["variables"])
    return HypothesisRecord(**payload)


def create_draft_plans(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Create draft experiment plans and mark plans failed when required columns are absent."""
    root = Path(config["_project_root"])
    inputs = config.get("inputs", {})
    outputs = config.get("outputs", {})
    top_path = resolve_path(inputs["top_k_hypotheses"], root)
    master_path = resolve_path(inputs["master_table"], root)
    plans_dir = resolve_path(outputs["plans_dir"], root)
    plans_dir.mkdir(parents=True, exist_ok=True)
    master_rows = read_csv(master_path) if master_path.exists() else []
    columns = set(master_rows[0].keys()) if master_rows else set()
    plans = []
    for payload in read_json(top_path) if top_path.exists() else []:
        hypothesis = _hypothesis(payload)
        plan = hypothesis_to_plan(hypothesis, config)
        required = [plan.outcome] + plan.predictors + plan.covariates
        missing = [name for name in required if name not in columns]
        if missing:
            plan.lock_status = ExperimentPlanStatus.failed
            plan.quality_gates["missing_variables"] = missing
        plan_payload = plan.model_dump(mode="json")
        write_json(plans_dir / f"{plan.experiment_id}_plan.json", plan_payload)
        plans.append(plan_payload)
    return plans
