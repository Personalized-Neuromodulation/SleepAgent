from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.experiment.agents.analysis_templates import (
    run_negative_controls,
    run_primary_tests,
    run_robustness_checks,
)
from sleep_ai_scientist.experiment.agents.llm import build_experiment_llm, load_prompt
from sleep_ai_scientist.schemas.experiment import (
    ExperimentPlan,
    MLAgentResult,
    NegativeControlResult,
    RobustnessCheckResult,
    StatsAgentResult,
)


class StatisticalModelAgent:
    """Uses LLM model judgment, then executes controlled statistical templates."""

    def __init__(self, config: dict[str, Any], *, output_dir: str | Path) -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.llm = build_experiment_llm(
            config.get("llm", {}),
            task_name="StatisticalModelAgent: select AnalysisDSL and controlled templates",
        )

    def run(
        self,
        plan: ExperimentPlan,
        *,
        enable_ml: bool,
        bootstrap_iterations: int,
    ) -> tuple[StatsAgentResult, MLAgentResult | None, list[RobustnessCheckResult], list[NegativeControlResult], dict[str, Any]]:
        model_review = self._llm_select_model(plan) if self.llm else self._llm_required_model(plan)
        tests = run_primary_tests(plan)
        robustness = run_robustness_checks(plan, tests, iterations=bootstrap_iterations)
        negative_controls = run_negative_controls(plan)
        passed = sum(1 for test in tests if test.passed)
        stats_result = StatsAgentResult(
            plan_id=plan.plan_id,
            hypothesis_id=plan.hypothesis_id,
            tests=tests,
            summary=f"{passed}/{len(tests)} primary statistical tests passed p<0.05.",
        )
        ml_result = self._ml_placeholder(plan) if enable_ml else None
        trace = {
            "model_review": model_review,
            "controlled_templates": {
                "primary": "spearman_correlation",
                "robustness": "bootstrap_spearman_ci",
                "negative_control": "spearman_negative_control",
            },
        }
        write_json(
            self.output_dir / f"{plan.plan_id}.statistical_model.json",
            {
                **trace,
                "stats_result": stats_result.model_dump(),
                "ml_result": ml_result.model_dump() if ml_result else None,
                "robustness_results": [item.model_dump() for item in robustness],
                "negative_control_results": [item.model_dump() for item in negative_controls],
            },
        )
        return stats_result, ml_result, robustness, negative_controls, trace

    def _llm_select_model(self, plan: ExperimentPlan) -> dict[str, Any]:
        system, user, max_tokens = load_prompt(
            "statistical_model",
            "select_model",
            {"execution_plan_json": json.dumps(plan.model_dump(), ensure_ascii=False, indent=2)},
        )
        return self.llm.call_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=float(self.config.get("llm", {}).get("temperature", 0.1)),
        )

    def _llm_required_model(self, plan: ExperimentPlan) -> dict[str, Any]:
        return {
            "status": "requires_llm_review",
            "reason": "Experiment LLM is disabled; controlled templates will still execute but model-choice judgment is absent.",
        }

    def _ml_placeholder(self, plan: ExperimentPlan) -> MLAgentResult:
        return MLAgentResult(
            plan_id=plan.plan_id,
            hypothesis_id=plan.hypothesis_id,
            outcome=plan.outcomes[0] if plan.outcomes else "",
            features=list(plan.predictors),
            model_type="not_run",
            notes="ML execution is intentionally gated; statistical templates provide the primary test.",
        )
