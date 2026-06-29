from __future__ import annotations

from typing import Any

from neuro_research_agent.agents.reviewer_agent.scoring import evaluate_innovations, evaluate_paradigms


class ReviewerAgent:
    """负责实验路线评分、创新点评分和结果质量审阅。"""

    name = "reviewer_agent"

    def evaluate_paradigms(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return evaluate_paradigms(*args, **kwargs)

    def evaluate_innovations(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return evaluate_innovations(*args, **kwargs)
