from __future__ import annotations

from pathlib import Path
from typing import Any

from neuro_research_agent.agents.analyst_agent.execution import run_generated_experiments
from neuro_research_agent.agents.analyst_agent.visualization import collect_connectome_figures, plot_paradigm_scores
from neuro_research_agent.agents.analyst_agent.robin_feedback import attach_local_feedback_prompts, feedback_source_metadata
from neuro_research_agent.agents.scientist_agent.innovation import build_innovation_process_document, update_innovations_from_execution


class AnalystAgent:
    """负责实验执行、结果解析、Robin 式反馈和图表汇总。"""

    name = "analyst_agent"

    def run_experiments(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return run_generated_experiments(*args, **kwargs)

    def update_innovations_from_execution(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = update_innovations_from_execution(*args, **kwargs)
        payload["feedback_mechanism_source"] = feedback_source_metadata()
        goal = str(args[0]) if args else ""
        return attach_local_feedback_prompts(payload, goal)

    def build_innovation_document(self, *args: Any, **kwargs: Any) -> str:
        return build_innovation_process_document(*args, **kwargs)

    def plot_scores(self, evaluations: list[dict[str, Any]], output_dir: Path) -> dict[str, str]:
        return plot_paradigm_scores(evaluations, output_dir)

    def collect_connectome_figures(self, execution_results: list[dict[str, Any]]) -> dict[str, str]:
        return collect_connectome_figures(execution_results)
