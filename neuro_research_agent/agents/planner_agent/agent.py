from __future__ import annotations

from typing import Any

from neuro_research_agent.agents.planner_agent.data_inventory import available_data_types, inspect_all_data
from neuro_research_agent.agents.planner_agent.fmri_preprocessing import ensure_processed_fmri_data, expected_processed_fmri_root
from neuro_research_agent.agents.planner_agent.paradigms import classify_paradigms


class PlannerAgent:
    """负责数据准备、清单扫描和候选实验路线规划。"""

    name = "planner_agent"

    def expected_processed_root(self, *args: Any, **kwargs: Any) -> Any:
        return expected_processed_fmri_root(*args, **kwargs)

    def ensure_fmri_data(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return ensure_processed_fmri_data(*args, **kwargs)

    def inspect_data(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return inspect_all_data(*args, **kwargs)

    def available_data_types(self, inventory: dict[str, Any]) -> set[str]:
        return available_data_types(inventory)

    def classify_paradigms(self, prompt: str, data_types: set[str]) -> list[dict[str, Any]]:
        return classify_paradigms(prompt, data_types)
