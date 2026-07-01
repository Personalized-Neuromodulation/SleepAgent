from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_json, write_json
from sleep_ai_scientist.schemas.experiment import ExperimentPlan, ExperimentPlanStatus


def plan_hash(plan_payload: dict[str, Any]) -> str:
    payload = dict(plan_payload)
    payload["locked_at"] = None
    payload["plan_hash"] = None
    payload["lock_status"] = "draft"
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def lock_plan(plan_payload: dict[str, Any]) -> dict[str, Any]:
    plan = ExperimentPlan(**plan_payload)
    if plan.lock_status == ExperimentPlanStatus.failed:
        return plan.model_dump(mode="json")
    payload = plan.model_dump(mode="json")
    payload["plan_hash"] = plan_hash(payload)
    payload["locked_at"] = datetime.now(timezone.utc).isoformat()
    payload["lock_status"] = ExperimentPlanStatus.locked.value
    return payload


def lock_draft_plans(config: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(config["_project_root"])
    outputs = config.get("outputs", {})
    plans_dir = resolve_path(outputs["plans_dir"], root)
    locked_dir = resolve_path(outputs["locked_plans_dir"], root)
    locked_dir.mkdir(parents=True, exist_ok=True)
    locked = []
    for path in sorted(plans_dir.glob("*_plan.json")):
        payload = lock_plan(read_json(path))
        write_json(locked_dir / path.name.replace("_plan.json", "_locked_plan.json"), payload)
        locked.append(payload)
    return locked
