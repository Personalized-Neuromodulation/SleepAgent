from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.benchmark.utils import input_path, model_dump_rows, output_path
from sleep_ai_scientist.common.io import read_csv, read_json, write_csv
from sleep_ai_scientist.schemas.benchmark import CriticBenchmarkScore


def agreement_score(critic_decision: str, expert_decision: str | None) -> float | None:
    if not expert_decision:
        return None
    normalized = {"accept": "accepted", "accepted": "accepted", "revise": "revised", "reject": "rejected"}
    critic = normalized.get(critic_decision, critic_decision)
    expert = normalized.get(expert_decision, expert_decision)
    if critic == expert:
        return 1.0
    compatible = {("revised", "exploratory_only"), ("exploratory_only", "revised"), ("hold", "revised"), ("revised", "hold")}
    return 0.5 if (critic, expert) in compatible else 0.0


def _expert_by_item(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    return {row.get("item_id", ""): row for row in read_csv(path) if row.get("item_id")}


def run_critic_benchmark(config: dict[str, Any]) -> list[CriticBenchmarkScore]:
    critic_dir = input_path(config, "critic_reviews_dir")
    experts = _expert_by_item(input_path(config, "expert_ratings"))
    scores = []
    for path in sorted(critic_dir.glob("*_critic_review.json")) if critic_dir.exists() else []:
        review = read_json(path)
        exp_id = review.get("experiment_id", "")
        expert = experts.get(exp_id) or experts.get(review.get("hypothesis_id", ""))
        expert_decision = expert.get("decision") if expert else None
        score = agreement_score(review.get("decision", ""), expert_decision)
        warnings = []
        if not review.get("decision"):
            warnings.append("missing_critic_decision")
        if not review.get("claim_strength"):
            warnings.append("missing_claim_strength")
        if review.get("causal_language_allowed"):
            warnings.append("causal_language_allowed")
        if review.get("decision") == "accepted" and review.get("claim_strength") == "not_supported":
            warnings.append("weak_result_accepted")
        self_score = round(1.0 - min(1.0, 0.25 * len(warnings)), 4)
        scores.append(
            CriticBenchmarkScore(
                experiment_id=exp_id,
                hypothesis_id=review.get("hypothesis_id", ""),
                critic_decision=review.get("decision", ""),
                expert_decision=expert_decision,
                agreement=(score == 1.0) if score is not None else None,
                agreement_score=score,
                critic_claim_strength=review.get("claim_strength"),
                expert_claim_strength=expert.get("claim_strength") if expert else None,
                overclaim_detected=bool(review.get("causal_language_allowed")),
                critic_score=self_score if score is None else round((self_score + score) / 2, 4),
                warnings=warnings,
            )
        )
    write_csv(output_path(config, "critic_benchmark_scores"), model_dump_rows(scores))
    return scores
