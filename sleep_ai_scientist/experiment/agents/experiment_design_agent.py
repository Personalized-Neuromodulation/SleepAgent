from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.experiment.design_constraints import plan_signature
from sleep_ai_scientist.experiment.agents.llm_adapter import build_experiment_llm, load_prompt
from sleep_ai_scientist.experiment.agents.planning import (
    build_experiment_plan_from_hypothesis,
    load_approved_variables,
    load_data_profile,
    load_hypotheses,
    load_variable_mappings,
)
from sleep_ai_scientist.hypothesis.testability import experiment_priority_score
from sleep_ai_scientist.schemas.experiment import ExperimentPlan


class ExperimentDesignAgent:
    """Builds concrete experiment plans from ranked hypotheses and observed data constraints."""

    def __init__(self, config: dict[str, Any], *, output_dir: str | Path) -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.llm = build_experiment_llm(
            config.get("llm", {}),
            task_name="ExperimentDesignAgent: review and refine experiment plan",
        )

    def run(
        self,
        *,
        hypothesis_pool_path: str | Path,
        data_profile_path: str | Path,
        approved_variables_path: str | Path | None,
        variable_mapping_path: str | Path | None,
        top_k: int,
        design_constraints: dict[str, Any] | None = None,
    ) -> list[ExperimentPlan]:
        hypotheses = sorted(load_hypotheses(hypothesis_pool_path), key=experiment_priority_score, reverse=True)
        profile = load_data_profile(data_profile_path)
        approved = load_approved_variables(approved_variables_path) if approved_variables_path else None
        mappings = load_variable_mappings(variable_mapping_path) if variable_mapping_path else None
        design_constraints = design_constraints or {}
        self._log_constraints(design_constraints)
        plans: list[ExperimentPlan] = []
        skipped: list[dict[str, str]] = []
        for hypothesis in hypotheses:
            if len(plans) >= top_k:
                break
            plan = build_experiment_plan_from_hypothesis(
                hypothesis,
                profile,
                approved_variables=approved,
                variable_mappings=mappings,
                max_predictors=int(self.config.get("max_predictors", 4)),
                max_outcomes=int(self.config.get("max_outcomes", 2)),
                design_constraints=design_constraints,
            )
            if plan_signature(plan) in set(design_constraints.get("avoid_signatures", [])):
                skipped.append({"hypothesis_id": hypothesis.hypothesis_id, "plan_id": plan.plan_id, "reason": "duplicate_experiment_signature"})
                self._log(f"[experiment:diversify] skipped_duplicate plan={plan.plan_id} hypothesis={hypothesis.hypothesis_id}")
                continue
            plans.append(plan)
        reviewed = [self._llm_design(plan, profile.model_dump(), design_constraints) if self.llm else self._mark_llm_required(plan) for plan in plans]
        for plan in reviewed:
            if plan_signature(plan) in set(design_constraints.get("avoid_signatures", [])):
                plan.metadata = {**plan.metadata, "constraint_violation": "duplicate_experiment_signature"}
                self._log(f"[experiment:diversify] duplicate_signature_after_llm plan={plan.plan_id}")
        write_json(self.output_dir / "experiment_design_constraints.json", design_constraints)
        write_json(self.output_dir / "experiment_design_agent.skipped.json", skipped)
        write_json(self.output_dir / "experiment_design_agent.plans.json", [plan.model_dump() for plan in reviewed])
        return reviewed

    def _llm_design(self, plan: ExperimentPlan, data_profile: dict[str, Any], design_constraints: dict[str, Any]) -> ExperimentPlan:
        system, user, max_tokens = load_prompt(
            "experiment_design",
            "design",
            {
                "plan_json": json.dumps(plan.model_dump(), ensure_ascii=False, indent=2),
                "data_profile_json": json.dumps(data_profile, ensure_ascii=False, indent=2),
                "design_constraints_json": json.dumps(design_constraints, ensure_ascii=False, indent=2),
            },
        )
        payload = self.llm.call_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=float(self.config.get("llm", {}).get("temperature", 0.1)),
        )
        metadata = dict(plan.metadata)
        metadata["llm_experiment_design"] = payload
        if payload.get("scientific_question"):
            plan.scientific_question = str(payload["scientific_question"])
        if isinstance(payload.get("primary_tests"), list) and payload["primary_tests"]:
            plan.primary_tests = payload["primary_tests"]
        if isinstance(payload.get("analysis_plan"), str):
            plan.analysis_plan = payload["analysis_plan"]
        plan.metadata = metadata
        return plan

    def _mark_llm_required(self, plan: ExperimentPlan) -> ExperimentPlan:
        metadata = dict(plan.metadata)
        metadata["llm_experiment_design"] = {
            "status": "requires_llm_review",
            "reason": "Experiment LLM is disabled; deterministic plan skeleton was produced without scientific judgment.",
        }
        plan.metadata = metadata
        return plan

    def _log_constraints(self, design_constraints: dict[str, Any]) -> None:
        self._log(
            "[experiment:constraints] "
            f"tried_signatures={len(design_constraints.get('avoid_signatures', []) or [])} "
            f"tested_hypotheses={len(design_constraints.get('tested_hypothesis_ids', []) or [])} "
            f"failed_tests={len(design_constraints.get('failed_tests', []) or [])} "
            f"negative_failed_predictors={len(design_constraints.get('negative_control_failed_predictors', []) or [])}"
        )

    def _log(self, message: str) -> None:
        if bool(self.config.get("verbose", False)):
            print(message, flush=True)
