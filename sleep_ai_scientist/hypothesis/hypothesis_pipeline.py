from __future__ import annotations

from typing import Any

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.hypothesis.generator import generate_candidate_hypotheses
from sleep_ai_scientist.hypothesis.lineage import save_lineage
from sleep_ai_scientist.hypothesis.registry import save_hypothesis_outputs
from sleep_ai_scientist.hypothesis.scorer import score_hypotheses
from sleep_ai_scientist.schemas.hypothesis import HypothesisStatus


def run_hypothesis_pipeline(config_path: str = "configs/hypothesis_config.yaml") -> dict[str, Any]:
    """Run deterministic scientific-loop hypothesis generation, screening, and top-K selection."""
    config = load_config(config_path)
    hypotheses = generate_candidate_hypotheses(config)
    scored = score_hypotheses(hypotheses, config)
    testable = [item for item in scored if item.pre_analysis_score and item.pre_analysis_score > 0]
    ranked = sorted(testable, key=lambda item: item.pre_analysis_score or 0.0, reverse=True)
    top_k_n = int(config.get("generation", {}).get("top_k", 5))
    top_k = ranked[:top_k_n]
    for item in top_k:
        item.status = HypothesisStatus.prioritized
    outputs = save_hypothesis_outputs(scored, top_k, config)
    outputs["hypothesis_lineage"] = save_lineage(scored, config)
    outputs["generated_hypotheses"] = len(hypotheses)
    outputs["screened_hypotheses"] = len(testable)
    outputs["top_k"] = len(top_k)
    return outputs
