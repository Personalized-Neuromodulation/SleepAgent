from __future__ import annotations

import math
import re
from collections import Counter
from statistics import mean
from typing import Any

from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.hypothesis.agents.embedding import LocalMiniLMEmbeddingClient, dense_cosine
from sleep_ai_scientist.hypothesis.agents.llm import build_llm_client, llm_enabled, load_prompt, normalize_llm_config
from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.hypothesis.agents.state import HypothesisSessionState
from sleep_ai_scientist.hypothesis.agents.tournament import seeded_glicko2_from_review_scores
from sleep_ai_scientist.schemas.hypothesis import Hypothesis, HypothesisReview, HypothesisStatus, ProximityEdge, ReviewType, ReviewVerdict


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def review_hypothesis(hypothesis: Hypothesis) -> HypothesisReview:
    """Deterministic review that approximates co-scientist's initial/full checks."""
    evidence_count = len(hypothesis.metadata.get("evidence_ids", []))
    citation_count = len(hypothesis.citations)
    assumptions = len(hypothesis.key_assumptions)
    novelty = min(10.0, 5.0 + len(set(hypothesis.key_assumptions)) * 0.8)
    correctness = min(10.0, 4.5 + evidence_count * 1.0 + citation_count * 0.4)
    testability = min(10.0, 4.5 + (2.0 if hypothesis.experimental_plan else 0.0) + assumptions * 0.5)
    score = mean([novelty, correctness, testability])
    verdict = ReviewVerdict.pass_ if score >= 6.0 else ReviewVerdict.uncertain
    return HypothesisReview(
        review_id=stable_id("review", hypothesis.hypothesis_id, "initial"),
        hypothesis_id=hypothesis.hypothesis_id,
        session_id=hypothesis.session_id,
        review_type=ReviewType.initial,
        verdict=verdict,
        novelty_score=round(novelty, 2),
        correctness_score=round(correctness, 2),
        testability_score=round(testability, 2),
        summary=f"Rule review score {score:.2f}/10 based on evidence, citations, and testability.",
        critique="Hypothesis is accepted for local tournament ranking if grounded and testable.",
        supporting_evidence=hypothesis.citations,
    )


def _coerce_verdict(value: Any) -> ReviewVerdict:
    text = str(value or "uncertain").strip().lower()
    if text == "pass":
        return ReviewVerdict.pass_
    if text == "fail":
        return ReviewVerdict.fail
    return ReviewVerdict.uncertain


def _score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(10.0, float(value)))
    except (TypeError, ValueError):
        return None


def _llm_review_hypothesis(
    hypothesis: Hypothesis,
    ollama_config: dict[str, Any],
    rlef_context: str = "",
    knowledge_context: str = "",
) -> list[HypothesisReview]:
    llm_config = normalize_llm_config(ollama_config)
    client = build_llm_client(llm_config)
    temperature = float(llm_config.get("temperature", 0.2))
    reviews: list[HypothesisReview] = []
    for review_type in [
        ReviewType.initial,
        ReviewType.full,
        ReviewType.deep_verification,
        ReviewType.simulation,
        ReviewType.observation,
    ]:
        system, prompt, max_tokens = load_prompt(
            "reflection",
            "review_stage",
            {
                "review_type": review_type.value,
                "title": hypothesis.title,
                "summary": hypothesis.summary,
                "content": hypothesis.content,
                "rationale": hypothesis.rationale,
                "experimental_plan": hypothesis.experimental_plan,
                "key_assumptions": hypothesis.key_assumptions,
                "citations": hypothesis.citations,
                "rlef_context": rlef_context,
                "knowledge_context": knowledge_context or "No knowledge graph context was provided.",
                "metadata": hypothesis.metadata,
            },
        )
        payload = client.call_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        reviews.append(
            HypothesisReview(
                review_id=stable_id("review", hypothesis.hypothesis_id, review_type.value),
                hypothesis_id=hypothesis.hypothesis_id,
                session_id=hypothesis.session_id,
                review_type=review_type,
                verdict=_coerce_verdict(payload.get("verdict")),
                novelty_score=_score(payload.get("novelty_score") or payload.get("noveltyScore")),
                correctness_score=_score(payload.get("correctness_score") or payload.get("correctnessScore")),
                testability_score=_score(payload.get("testability_score") or payload.get("testabilityScore")),
                safety_flag=bool(payload.get("safety_flag") or payload.get("safetyFlag", False)),
                summary=str(payload.get("summary", "")),
                critique="\n".join(payload.get("critique", [])) if isinstance(payload.get("critique"), list) else str(payload.get("critique", "")),
                supporting_evidence=[str(item) for item in payload.get("supporting_evidence", payload.get("supportingEvidence", []))],
            )
        )
    return reviews


def _activate_from_reviews(registry: HypothesisRegistry, hypothesis: Hypothesis, reviews: list[HypothesisReview]) -> None:
    if reviews[0].verdict == ReviewVerdict.fail or any(review.safety_flag for review in reviews):
        registry.set_status(hypothesis.hypothesis_id, HypothesisStatus.rejected)
        return
    novelty = _best_score([review.novelty_score for review in reviews])
    correctness = _best_score([review.correctness_score for review in reviews])
    testability = _best_score([review.testability_score for review in reviews])
    rating, rd, volatility = seeded_glicko2_from_review_scores(novelty, correctness, testability)
    registry.update_rating(hypothesis.hypothesis_id, rating, rating_deviation=rd, volatility=volatility)
    registry.set_status(hypothesis.hypothesis_id, HypothesisStatus.active)


def _best_score(scores: list[float | None]) -> float | None:
    available = [score for score in scores if score is not None]
    return max(available) if available else None


def run_reflection(
    registry: HypothesisRegistry,
    ollama_config: dict[str, Any] | None = None,
    rlef_context: str = "",
    knowledge_context: str = "",
) -> list[HypothesisReview]:
    reviews: list[HypothesisReview] = []
    for hypothesis in registry.pending_review():
        if llm_enabled(ollama_config):
            staged_reviews = _llm_review_hypothesis(
                hypothesis,
                ollama_config,
                rlef_context=rlef_context,
                knowledge_context=knowledge_context,
            )
            for review in staged_reviews:
                registry.add_review(review)
            _activate_from_reviews(registry, hypothesis, staged_reviews)
            reviews.extend(staged_reviews)
            continue

        review = review_hypothesis(hypothesis)
        registry.add_review(review)
        _activate_from_reviews(registry, hypothesis, [review])
        reviews.append(review)
    return reviews


def text_vector(text: str) -> Counter[str]:
    return Counter(token.lower() for token in TOKEN_RE.findall(text))


def cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def hypothesis_vector(hypothesis: Hypothesis) -> Counter[str]:
    return text_vector(f"{hypothesis.title} {hypothesis.summary} {' '.join(hypothesis.key_assumptions)}")


def compute_proximity_edges(
    hypotheses: list[Hypothesis],
    *,
    session_id: str,
    edge_threshold: float = 0.45,
) -> list[ProximityEdge]:
    vectors = {item.hypothesis_id: hypothesis_vector(item) for item in hypotheses}
    edges: list[ProximityEdge] = []
    for index, left in enumerate(hypotheses):
        for right in hypotheses[index + 1 :]:
            score = cosine_similarity(vectors[left.hypothesis_id], vectors[right.hypothesis_id])
            if score >= edge_threshold:
                edges.append(
                    ProximityEdge(
                        session_id=session_id,
                        hypothesis_a_id=left.hypothesis_id,
                        hypothesis_b_id=right.hypothesis_id,
                        similarity=round(score, 4),
                    )
                )
    return edges


def reject_near_duplicates(
    registry: HypothesisRegistry,
    *,
    duplicate_threshold: float = 0.92,
    embedding_config: dict[str, Any] | None = None,
) -> list[str]:
    rejected: list[str] = []
    active_or_pending = [
        item
        for item in registry.all()
        if item.status in {HypothesisStatus.active, HypothesisStatus.pending_review}
    ]
    if embedding_config and bool(embedding_config.get("enabled", False)):
        client = LocalMiniLMEmbeddingClient(str(embedding_config.get("model", "sentence-transformers/all-MiniLM-L6-v2")))
        texts = [f"{item.title} {item.summary} {' '.join(item.key_assumptions)}" for item in active_or_pending]
        dense_vectors = dict(zip([item.hypothesis_id for item in active_or_pending], client.embed(texts)))
        for index, left in enumerate(active_or_pending):
            if left.hypothesis_id in rejected:
                continue
            for right in active_or_pending[index + 1 :]:
                if right.hypothesis_id in rejected:
                    continue
                score = dense_cosine(dense_vectors[left.hypothesis_id], dense_vectors[right.hypothesis_id])
                if score >= duplicate_threshold:
                    loser = left if left.elo_rating < right.elo_rating else right
                    registry.set_status(loser.hypothesis_id, HypothesisStatus.rejected)
                    rejected.append(loser.hypothesis_id)
        registry.proximity_edges = compute_proximity_edges(active_or_pending, session_id=registry.session_id)
        return rejected

    vectors = {item.hypothesis_id: hypothesis_vector(item) for item in active_or_pending}
    for index, left in enumerate(active_or_pending):
        if left.hypothesis_id in rejected:
            continue
        for right in active_or_pending[index + 1 :]:
            if right.hypothesis_id in rejected:
                continue
            score = cosine_similarity(vectors[left.hypothesis_id], vectors[right.hypothesis_id])
            if score >= duplicate_threshold:
                loser = left if left.elo_rating < right.elo_rating else right
                registry.set_status(loser.hypothesis_id, HypothesisStatus.rejected)
                rejected.append(loser.hypothesis_id)
    registry.proximity_edges = compute_proximity_edges(active_or_pending, session_id=registry.session_id)
    return rejected


class ReviewAgent:
    name = "ReviewAgent"

    def run(self, state: HypothesisSessionState) -> HypothesisSessionState:
        hypothesis_cfg = state.config.get("hypothesis", {})
        context_block = "\n\n".join(
            block
            for block in [
                state.context_blocks.get("research_question", ""),
                state.context_blocks.get("knowledge_graph", ""),
                state.context_blocks.get("rlef_context", ""),
            ]
            if block
        )
        reviews = run_reflection(
            state.registry,
            ollama_config=state.config.get("_selected_llm", {}),
            rlef_context=state.context_blocks.get("rlef_context", ""),
            knowledge_context=context_block,
        )
        state.reviews.extend(reviews)
        rejected = reject_near_duplicates(
            state.registry,
            duplicate_threshold=float(hypothesis_cfg.get("duplicate_threshold", 0.92)),
            embedding_config=state.config.get("embedding", {}),
        )
        state.rejected_duplicates.extend(item for item in rejected if item not in state.rejected_duplicates)
        return state
