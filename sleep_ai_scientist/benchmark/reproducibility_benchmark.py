from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.benchmark.utils import model_dump_rows, output_path
from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import write_csv
from sleep_ai_scientist.schemas.benchmark import ReproducibilityScore


ARTIFACTS = {
    "foundation": ["data/foundation/feature_registry.csv", "data/foundation/multimodal_master_table.csv", "configs/foundation_config.yaml", "reports/data_foundation_report.md"],
    "grounding": ["outputs/grounding/evidence_table.csv", "outputs/grounding/evidence_to_variable_map.yaml", "configs/grounding_config.yaml", "reports/grounding_report.md"],
    "hypotheses": ["outputs/hypotheses/hypothesis_pool.json", "outputs/hypotheses/top_k_hypotheses.json", "configs/hypothesis_config.yaml"],
    "experiments": ["outputs/experiments/locked_plans", "outputs/experiments/results", "outputs/experiments/critic_reviews", "configs/experiment_config.yaml", "reports/scientific_loop_report.md"],
    "co_scientist": ["outputs/co_scientist/co_scientist_top_k.json", "outputs/co_scientist/ranking_results.csv", "configs/co_scientist_config.yaml", "reports/co_scientist_report.md"],
}


def run_reproducibility_benchmark(config: dict[str, Any]) -> list[ReproducibilityScore]:
    root = Path(config["_project_root"])
    memory = resolve_path("outputs/memory/scientific_memory.jsonl", root)
    scores = []
    for artifact, required in ARTIFACTS.items():
        existing = []
        missing = []
        for item in required:
            path = resolve_path(item, root)
            exists = path.exists() and (path.is_dir() or path.stat().st_size >= 0)
            (existing if exists else missing).append(item)
        has_config = any(item.startswith("configs/") and item in existing for item in required)
        has_report = any(item.startswith("reports/") and item in existing for item in required)
        score = round((len(existing) / len(required)) * 0.7 + (0.1 if has_config else 0) + (0.1 if has_report else 0) + (0.1 if memory.exists() else 0), 4)
        scores.append(
            ReproducibilityScore(
                artifact_id=artifact,
                artifact_type=artifact,
                required_files=required,
                existing_files=existing,
                missing_files=missing,
                has_config=has_config,
                has_schema=True,
                has_report=has_report,
                has_audit_trace=memory.exists(),
                reproducibility_score=min(1.0, score),
                warnings=[f"missing:{item}" for item in missing],
            )
        )
    write_csv(output_path(config, "reproducibility_scores"), model_dump_rows(scores))
    return scores
