from __future__ import annotations

from typing import Any

from sleep_ai_scientist.benchmark.utils import input_path, load_json_list, model_dump_rows, output_path
from sleep_ai_scientist.common.io import read_csv, write_csv
from sleep_ai_scientist.schemas.benchmark import CoScientistBenchmarkScore


def run_co_scientist_benchmark(config: dict[str, Any]) -> list[CoScientistBenchmarkScore]:
    scientific_top = {item.get("hypothesis_id") for item in load_json_list(input_path(config, "top_k_hypotheses"))}
    co_top = {item.get("hypothesis_id"): item for item in load_json_list(input_path(config, "co_scientist_top_k"))}
    ranking = {row.get("hypothesis_id"): row for row in read_csv(input_path(config, "co_scientist_ranking_results"))} if input_path(config, "co_scientist_ranking_results").exists() else {}
    reflections = {item.get("hypothesis_id"): item for item in load_json_list(input_path(config, "co_scientist_reflection_reviews"))}
    clusters = load_json_list(input_path(config, "co_scientist_candidate_pool"))
    evolved = {item.get("hypothesis_id"): item for item in load_json_list(input_path(config, "co_scientist_evolved_hypotheses"))}
    scores = []
    for hid, hypothesis in co_top.items():
        row = ranking.get(hid, {})
        reflection = reflections.get(hid, {})
        evolved_payload = evolved.get(hid, {})
        parent_ids = evolved_payload.get("parent_ids", [])
        warnings = []
        if evolved_payload and not parent_ids:
            warnings.append("evolved_missing_parent_ids")
        if "posthoc" in str(hypothesis.get("source", "")) and hypothesis.get("evidence_level") == "confirmatory":
            warnings.append("posthoc_confirmatory_mislabel")
        diversity = min(1.0, len(set(hypothesis.get("required_modalities", []))) / 3)
        improvement = 0.7 if hid not in scientific_top else 0.5
        reflection_score = float(reflection.get("overall_reflection_score") or 0.5)
        ranking_score = max(0.0, 1.0 - (float(row.get("final_rank") or 99) - 1) / 20) if row else None
        total = round(0.35 * (ranking_score or 0.5) + 0.30 * reflection_score + 0.20 * diversity + 0.15 * improvement, 4)
        scores.append(
            CoScientistBenchmarkScore(
                hypothesis_id=hid,
                in_scientific_loop_top_k=hid in scientific_top,
                in_co_scientist_top_k=True,
                ranking_score=ranking_score,
                reflection_score=reflection_score,
                cluster_id=None,
                evolved=hid in evolved,
                parent_ids=parent_ids,
                diversity_contribution_score=round(diversity, 4),
                improvement_over_scientific_loop_score=improvement,
                co_scientist_score=total,
                warnings=warnings,
            )
        )
    write_csv(output_path(config, "co_scientist_benchmark_scores"), model_dump_rows(scores))
    return scores
