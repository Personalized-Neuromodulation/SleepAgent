from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import write_csv, write_json
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, RankingPair, RankingResult, ReflectionReview


def composite_score(hypothesis: HypothesisRecord, review: ReflectionReview | None) -> float:
    components = hypothesis.score_components or {}
    score = 0.0
    score += 0.25 * (hypothesis.pre_analysis_score or 0.0)
    score += 0.18 * components.get("evidence_strength", 0.5)
    score += 0.16 * components.get("data_testability", 0.5)
    score += 0.18 * (review.overall_reflection_score if review else 0.5)
    score += 0.10 * components.get("novelty_proxy", 0.5)
    score += 0.07 * min(1.0, len(hypothesis.required_modalities) / 3)
    score += 0.06 * components.get("confound_controllability", 0.5)
    if review and review.recommendation == "reject":
        score *= 0.2
    if review and review.recommendation == "hold":
        score *= 0.7
    return round(score, 6)


def _elo_update(elo_a: float, elo_b: float, outcome_a: float, k_factor: float) -> tuple[float, float]:
    expected_a = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
    expected_b = 1 - expected_a
    return elo_a + k_factor * (outcome_a - expected_a), elo_b + k_factor * ((1 - outcome_a) - expected_b)


def pairwise_rank(
    hypotheses: list[HypothesisRecord],
    reviews: list[ReflectionReview],
    representative_ids: set[str] | None,
    config: dict[str, Any],
) -> tuple[list[RankingPair], list[RankingResult]]:
    review_by_id = {item.hypothesis_id: item for item in reviews}
    max_pairs = int(config.get("ranking", {}).get("max_pairs", 300))
    initial = float(config.get("ranking", {}).get("initial_elo", 1500))
    k_factor = float(config.get("ranking", {}).get("k_factor", 32))
    ordered = sorted(hypotheses, key=lambda item: (item.hypothesis_id not in (representative_ids or set()), item.hypothesis_id))
    pairs: list[RankingPair] = []
    stats = {item.hypothesis_id: RankingResult(hypothesis_id=item.hypothesis_id, elo_score=initial) for item in hypotheses}
    for index, (a, b) in enumerate(combinations(ordered, 2), start=1):
        if len(pairs) >= max_pairs:
            break
        score_a = composite_score(a, review_by_id.get(a.hypothesis_id))
        score_b = composite_score(b, review_by_id.get(b.hypothesis_id))
        if abs(score_a - score_b) < 0.02:
            winner = None
            outcome = 0.5
            reason = "draw: composite scores are close"
            stats[a.hypothesis_id].tournament_draws += 1
            stats[b.hypothesis_id].tournament_draws += 1
        elif score_a > score_b:
            winner = a.hypothesis_id
            outcome = 1.0
            reason = "higher pre-analysis/reflection composite score"
            stats[a.hypothesis_id].tournament_wins += 1
            stats[b.hypothesis_id].tournament_losses += 1
        else:
            winner = b.hypothesis_id
            outcome = 0.0
            reason = "higher pre-analysis/reflection composite score"
            stats[b.hypothesis_id].tournament_wins += 1
            stats[a.hypothesis_id].tournament_losses += 1
        stats[a.hypothesis_id].elo_score, stats[b.hypothesis_id].elo_score = _elo_update(
            stats[a.hypothesis_id].elo_score, stats[b.hypothesis_id].elo_score, outcome, k_factor
        )
        pairs.append(RankingPair(pair_id=f"P{index:04d}", hypothesis_a=a.hypothesis_id, hypothesis_b=b.hypothesis_id, winner=winner, reason=reason, score_a=score_a, score_b=score_b))
    ranked = sorted(stats.values(), key=lambda item: item.elo_score, reverse=True)
    rejected = {item.hypothesis_id for item in reviews if item.recommendation == "reject"}
    final_rank = 1
    for item in ranked:
        item.elo_score = round(item.elo_score, 4)
        if item.hypothesis_id in rejected:
            item.final_rank = 9999
            item.rank_reason = "excluded from final top-K because reflection rejected it"
        else:
            item.final_rank = final_rank
            item.rank_reason = "ranked by deterministic Elo tournament"
            final_rank += 1
    return pairs, sorted(ranked, key=lambda item: item.final_rank)


def run_ranking_agent(
    hypotheses: list[HypothesisRecord],
    reviews: list[ReflectionReview],
    representative_ids: set[str] | None,
    config: dict[str, Any],
) -> tuple[list[RankingPair], list[RankingResult]]:
    pairs, results = pairwise_rank(hypotheses, reviews, representative_ids, config)
    root = Path(config["_project_root"])
    outputs = config.get("outputs", {})
    write_json(resolve_path(outputs["ranking_pairs"], root), [item.model_dump(mode="json") for item in pairs])
    write_csv(resolve_path(outputs["ranking_results"], root), [item.model_dump(mode="json") for item in results])
    return pairs, results
