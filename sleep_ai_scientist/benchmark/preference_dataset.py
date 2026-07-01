from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.benchmark.utils import output_path
from sleep_ai_scientist.common.io import ensure_parent
from sleep_ai_scientist.schemas.benchmark import ExpertRating, HypothesisQualityScore, PairwisePreference


def _rating_score(rating: ExpertRating) -> float:
    values = [
        rating.mechanism_plausibility,
        rating.data_testability,
        rating.evidence_grounding,
        rating.novelty,
        rating.clinical_value,
        rating.statistical_feasibility,
        rating.priority_for_analysis,
    ]
    values = [item for item in values if item is not None]
    return sum(values) / len(values) if values else 0.0


def build_pairwise_preferences(
    config: dict[str, Any],
    expert_ratings: list[ExpertRating],
    quality_scores: list[HypothesisQualityScore],
) -> list[PairwisePreference]:
    max_pairs = int(config.get("pairwise_preference", {}).get("max_pairs", 200))
    preferences: list[PairwisePreference] = []
    if expert_ratings:
        sorted_ratings = sorted(expert_ratings, key=_rating_score, reverse=True)
        for index in range(min(len(sorted_ratings) - 1, max_pairs)):
            a = sorted_ratings[index]
            b = sorted_ratings[index + 1]
            preferences.append(
                PairwisePreference(
                    pair_id=f"EXPREF_{index + 1:04d}",
                    expert_id=a.expert_id,
                    item_type=a.item_type if a.item_type in {"hypothesis", "critic_review", "experiment_plan"} else "hypothesis",
                    item_a=a.item_id,
                    item_b=b.item_id,
                    preferred_item=a.item_id if _rating_score(a) >= _rating_score(b) else b.item_id,
                    preference_strength=2,
                    reason="Higher expert priority and grounding dimensions.",
                    source="expert",
                )
            )
    else:
        sorted_scores = sorted(quality_scores, key=lambda item: item.overall_quality_score, reverse=True)
        for index in range(min(len(sorted_scores) - 1, max_pairs)):
            a = sorted_scores[index]
            b = sorted_scores[index + 1]
            preferences.append(
                PairwisePreference(
                    pair_id=f"RULE_{index + 1:04d}",
                    item_type="hypothesis",
                    item_a=a.hypothesis_id,
                    item_b=b.hypothesis_id,
                    preferred_item=a.hypothesis_id if a.overall_quality_score >= b.overall_quality_score else b.hypothesis_id,
                    preference_strength=1,
                    reason="Rule-based preference from benchmark quality score.",
                    source="rule_based",
                )
            )
    return preferences


def write_pairwise_preferences(config: dict[str, Any], preferences: list[PairwisePreference]) -> str:
    path = output_path(config, "pairwise_preferences")
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for item in preferences:
            f.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n")
    return str(path)


def run_preference_dataset(config: dict[str, Any], expert_ratings: list[ExpertRating], quality_scores: list[HypothesisQualityScore]) -> list[PairwisePreference]:
    prefs = build_pairwise_preferences(config, expert_ratings, quality_scores)
    write_pairwise_preferences(config, prefs)
    return prefs
