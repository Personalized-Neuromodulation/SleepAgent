from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_json
from sleep_ai_scientist.schemas.experiment import ExperimentPlan


def plan_signature(plan_or_payload: ExperimentPlan | dict[str, Any]) -> str:
    if isinstance(plan_or_payload, ExperimentPlan):
        predictors = plan_or_payload.predictors
        outcomes = plan_or_payload.outcomes
        covariates = plan_or_payload.covariates
    else:
        payload = plan_or_payload.get("plan", plan_or_payload)
        predictors = payload.get("predictors", [])
        outcomes = payload.get("outcomes", [])
        covariates = payload.get("covariates", [])
    return "|".join(
        [
            ",".join(sorted(str(item) for item in predictors)),
            ",".join(sorted(str(item) for item in outcomes)),
            ",".join(sorted(str(item) for item in covariates)),
        ]
    )


def build_experiment_design_constraints(
    *,
    previous_result_paths: list[str | Path] | None = None,
    previous_feedback_paths: list[str | Path] | None = None,
) -> dict[str, Any]:
    avoid_signatures: set[str] = set()
    failed_tests: list[dict[str, Any]] = []
    negative_failed_predictors: set[str] = set()
    validated_plan_ids: set[str] = set()
    tested_hypothesis_ids: set[str] = set()
    tested_plan_ids: set[str] = set()

    for path in previous_result_paths or []:
        for bundle in _read_list(path):
            if not isinstance(bundle, dict):
                continue
            plan = bundle.get("plan", bundle)
            hypothesis_id = str(plan.get("hypothesis_id") or bundle.get("hypothesis_id") or "").strip()
            plan_id = str(plan.get("plan_id") or bundle.get("plan_id") or "").strip()
            if hypothesis_id:
                tested_hypothesis_ids.add(hypothesis_id)
            if plan_id:
                tested_plan_ids.add(plan_id)
            signature = plan_signature(plan)
            if signature.strip("|"):
                avoid_signatures.add(signature)
            for test in (bundle.get("stats_result") or {}).get("tests", []) or []:
                if isinstance(test, dict) and not bool(test.get("passed", False)):
                    failed_tests.append(
                        {
                            "predictor": test.get("predictor", ""),
                            "outcome": test.get("outcome", ""),
                            "method": test.get("method", ""),
                            "p_value": test.get("p_value"),
                            "effect": test.get("effect"),
                        }
                    )
            for result in bundle.get("negative_control_results", []) or []:
                if isinstance(result, dict) and not bool(result.get("passed", False)):
                    predictor = str(result.get("predictor", "")).strip()
                    if predictor:
                        negative_failed_predictors.add(predictor)

    for path in previous_feedback_paths or []:
        for record in _read_list(path):
            if not isinstance(record, dict):
                continue
            if bool(record.get("validated", False)) or float(record.get("computed_reward", 0.0) or 0.0) >= 0.7:
                plan_id = str(record.get("plan_id", "")).strip()
                if plan_id:
                    validated_plan_ids.add(plan_id)
            metadata = record.get("metadata") or {}
            for finding in metadata.get("critic_findings", []) or []:
                if isinstance(finding, dict) and str(finding.get("category", "")).lower() in {"negative_control", "confounds"}:
                    predictor = str(finding.get("predictor", "")).strip()
                    if predictor:
                        negative_failed_predictors.add(predictor)

    return {
        "avoid_signatures": sorted(avoid_signatures),
        "failed_tests": failed_tests,
        "negative_control_failed_predictors": sorted(negative_failed_predictors),
        "tested_hypothesis_ids": sorted(tested_hypothesis_ids),
        "tested_plan_ids": sorted(tested_plan_ids),
        "validated_plan_ids": sorted(validated_plan_ids),
        "recommended_design_shifts": [
            "avoid exact repeat of tested predictor/outcome/covariate signatures",
            "prefer untested available predictors or outcomes when scientifically coherent",
            "if reusing a negative-control-failed predictor, make the design explicitly confound-focused",
            "if no non-duplicate measurable plan exists, select the next-ranked hypothesis",
        ],
    }


def _read_list(path: str | Path) -> list[Any]:
    target = Path(path)
    if not target.exists() or target.stat().st_size == 0:
        return []
    payload = read_json(target)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("results", "feedback", "records"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []
