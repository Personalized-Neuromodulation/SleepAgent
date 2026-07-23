from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.experiment.agents.llm_adapter import build_experiment_llm, load_prompt
from sleep_ai_scientist.experiment.agents.planning import (
    build_experiment_plan_from_hypothesis,
    load_approved_variables,
    load_data_profile,
    load_hypotheses,
    load_variable_mappings,
)
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
    ) -> list[ExperimentPlan]:
        hypotheses = sorted(load_hypotheses(hypothesis_pool_path), key=lambda item: item.elo_rating, reverse=True)[:top_k]
        profile = load_data_profile(data_profile_path)
        approved = load_approved_variables(approved_variables_path) if approved_variables_path else None
        mappings = load_variable_mappings(variable_mapping_path) if variable_mapping_path else None
        plans = [
            build_experiment_plan_from_hypothesis(
                hypothesis,
                profile,
                approved_variables=approved,
                variable_mappings=mappings,
                max_predictors=int(self.config.get("max_predictors", 4)),
                max_outcomes=int(self.config.get("max_outcomes", 2)),
            )
            for hypothesis in hypotheses
        ]
        reviewed = [self._llm_design(plan, profile.model_dump()) if self.llm else self._mark_llm_required(plan) for plan in plans]
        write_json(self.output_dir / "experiment_design_agent.plans.json", [plan.model_dump() for plan in reviewed])
        return reviewed

    def _llm_design(self, plan: ExperimentPlan, data_profile: dict[str, Any]) -> ExperimentPlan:
        system, user, max_tokens = load_prompt(
            "experiment_design",
            "design",
            {
                "plan_json": json.dumps(plan.model_dump(), ensure_ascii=False, indent=2),
                "data_profile_json": json.dumps(data_profile, ensure_ascii=False, indent=2),
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
