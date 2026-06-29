from __future__ import annotations

from pathlib import Path
from typing import Any

from neuro_research_agent.agents.coder_agent.code_generation import generate_experiment_code
from neuro_research_agent.agents.coder_agent.code_search import search_code_for_paradigm


class CoderAgent:
    """负责检索参考代码、生成每个实验的可执行 py 代码。"""

    name = "coder_agent"

    def search_code(self, paradigm_id: str, prompt: str, max_results: int, allow_network: bool) -> list[dict[str, Any]]:
        return search_code_for_paradigm(paradigm_id, prompt, max_results=max_results, allow_network=allow_network)

    def generate_code(self, paradigm: dict[str, Any], out_dir: Path, linked_innovations: list[dict[str, Any]]) -> Path:
        return generate_experiment_code(paradigm, out_dir, linked_innovations=linked_innovations)
