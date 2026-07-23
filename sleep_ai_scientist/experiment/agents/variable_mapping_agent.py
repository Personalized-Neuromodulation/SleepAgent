from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.experiment.agents.llm_adapter import build_experiment_llm, load_prompt
from sleep_ai_scientist.schemas.data_profile import DataProfile
from sleep_ai_scientist.schemas.experiment import ExperimentPlan


class VariableMappingAgent:
    """Refreshes concept-to-feature mappings against the real analysis-ready profile."""

    def __init__(self, config: dict[str, Any], *, output_dir: str | Path) -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.llm = build_experiment_llm(
            config.get("llm", {}),
            task_name="VariableMappingAgent: judge concept-to-feature mappings",
        )

    def run(self, plan: ExperimentPlan, data_profile: DataProfile) -> ExperimentPlan:
        profile_by_name = {feature.feature_name: feature for feature in data_profile.features}
        for variable in plan.variables:
            feature = profile_by_name.get(variable.name)
            if feature is None:
                variable.notes = "Variable requested by plan but unavailable in current data profile."
                variable.mapping_confidence = min(variable.mapping_confidence, 0.2)
                continue
            variable.source_file = feature.source_file
            variable.source_column = feature.source_column or feature.feature_name
            variable.modality = feature.modality
            variable.approved = feature.approved
            variable.missing_rate = feature.missing_rate
            variable.n_available = feature.n_available
        review = self._llm_review(plan, data_profile) if self.llm else self._llm_required_review(plan)
        metadata = dict(plan.metadata)
        metadata["variable_mapping_review"] = review
        plan.metadata = metadata
        write_json(self.output_dir / f"{plan.plan_id}.variable_mapping.json", review)
        return plan

    def _llm_review(self, plan: ExperimentPlan, data_profile: DataProfile) -> dict[str, Any]:
        system, user, max_tokens = load_prompt(
            "variable_mapping",
            "map_variables",
            {
                "plan_json": json.dumps(plan.model_dump(), ensure_ascii=False, indent=2),
                "data_profile_json": json.dumps(data_profile.model_dump(), ensure_ascii=False, indent=2),
            },
        )
        return self.llm.call_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=float(self.config.get("llm", {}).get("temperature", 0.1)),
        )

    def _llm_required_review(self, plan: ExperimentPlan) -> dict[str, Any]:
        return {
            "status": "requires_llm_review",
            "candidate_mappings": [
                {
                    "variable": variable.name,
                    "role": variable.role.value,
                    "source_file": variable.source_file,
                    "source_column": variable.source_column,
                    "modality": variable.modality,
                    "approved": variable.approved,
                    "n_available": variable.n_available,
                }
                for variable in plan.variables
            ],
            "reason": "Experiment LLM is disabled; mappings are populated from data profile but not scientifically adjudicated.",
        }
