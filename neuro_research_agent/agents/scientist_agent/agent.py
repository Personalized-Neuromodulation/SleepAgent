from __future__ import annotations

from typing import Any

from neuro_research_agent.agents.scientist_agent.innovation import build_innovation_process_document, derive_innovation_points
from neuro_research_agent.agents.scientist_agent.literature import retrieve_literature_bundle


class ScientistAgent:
    """负责文献理解、创新点生成、自我反思和 pairwise 排序。"""

    name = "scientist_agent"

    def retrieve_literature(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return retrieve_literature_bundle(*args, **kwargs)

    def derive_innovations(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return derive_innovation_points(*args, **kwargs)

    def build_innovation_document(self, *args: Any, **kwargs: Any) -> str:
        return build_innovation_process_document(*args, **kwargs)
