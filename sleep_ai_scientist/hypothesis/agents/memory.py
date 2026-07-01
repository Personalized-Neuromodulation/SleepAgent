from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_json, write_json
from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field
from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.hypothesis.agents.embedding import LocalMiniLMEmbeddingClient, dense_cosine
from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.hypothesis.agents.tournament import Glicko2State, compute_glicko2_update
from sleep_ai_scientist.schemas.hypothesis import Hypothesis, utc_now_iso


POSITIVE_TERMS = {
    "confirm", "confirmed", "validate", "validated", "support", "supports",
    "supported", "replicate", "replicated", "success", "successful",
    "effective", "significant", "improved", "increase", "increased",
    "reduced", "positive", "promising", "strong", "robust", "consistent",
}

NEGATIVE_TERMS = {
    "refute", "refuted", "reject", "rejected", "fail", "failed", "failure",
    "ineffective", "contradict", "contradicted", "negative", "poor", "weak",
    "inconsistent", "unreliable", "no effect", "no significant",
    "not significant", "does not", "did not", "unsafe",
}

STRONG_SIGNAL_THRESHOLD = 0.3
REWARD_WIN_THRESHOLD = 0.33
STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has",
    "were", "been", "into", "will", "would", "could", "should", "sleep",
}


class ExperimentalFeedback(BaseModel):
    feedback_id: str
    hypothesis_id: str
    session_id: str
    feedback_text: str
    novelty_score: float | None = None
    correctness_score: float | None = None
    testability_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    computed_reward: float = 0.0
    recorded_by: str = "human"
    created_at: str = Field(default_factory=utc_now_iso)


class RewardMemoryRecord(BaseModel):
    memory_id: str
    hypothesis_id: str
    session_id: str
    feedback_summary: str
    mechanistic_keywords: list[str] = Field(default_factory=list)
    computed_reward: float
    hypothesis_title: str = ""
    hypothesis_summary: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


def analyze_sentiment(text: str) -> float:
    lower = text.lower()
    words = set(re.split(r"\W+", lower))
    pos = sum(1 for term in POSITIVE_TERMS if (term in lower if " " in term else term in words))
    neg = sum(1 for term in NEGATIVE_TERMS if (term in lower if " " in term else term in words))
    total = pos + neg
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / total))


def extract_reward_from_feedback(
    feedback_text: str,
    novelty_score: float | None = None,
    correctness_score: float | None = None,
    testability_score: float | None = None,
) -> float:
    sentiment = analyze_sentiment(feedback_text)
    scores = [novelty_score, correctness_score, testability_score]
    if all(score is not None for score in scores):
        score_avg = (sum(float(score) for score in scores if score is not None) / 30.0) - 1.0
        reward = 0.4 * sentiment + 0.6 * score_avg
    else:
        reward = sentiment
    return round(max(-1.0, min(1.0, reward)), 6)


def load_experimental_feedback(path: Path) -> list[ExperimentalFeedback]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, Any]]
    if path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        payload = read_json(path)
        rows = payload if isinstance(payload, list) else payload.get("feedback", [])
    feedbacks: list[ExperimentalFeedback] = []
    for row in rows:
        reward = row.get("computed_reward")
        if reward is None:
            reward = extract_reward_from_feedback(
                str(row.get("feedback_text") or row.get("feedbackText") or ""),
                row.get("novelty_score") or row.get("noveltyScore"),
                row.get("correctness_score") or row.get("correctnessScore"),
                row.get("testability_score") or row.get("testabilityScore"),
            )
        feedbacks.append(
            ExperimentalFeedback(
                feedback_id=str(row.get("feedback_id") or row.get("id") or stable_id("feedback", row)),
                hypothesis_id=str(row.get("hypothesis_id") or row.get("hypothesisId") or ""),
                session_id=str(row.get("session_id") or row.get("sessionId") or ""),
                feedback_text=str(row.get("feedback_text") or row.get("feedbackText") or ""),
                novelty_score=row.get("novelty_score") or row.get("noveltyScore"),
                correctness_score=row.get("correctness_score") or row.get("correctnessScore"),
                testability_score=row.get("testability_score") or row.get("testabilityScore"),
                metadata=row.get("metadata", {}),
                computed_reward=float(reward),
                recorded_by=str(row.get("recorded_by") or row.get("recordedBy") or "human"),
                created_at=str(row.get("created_at") or row.get("createdAt") or utc_now_iso()),
            )
        )
    return feedbacks


def apply_feedback_as_glicko2_match(hypothesis: Hypothesis, reward: float) -> Glicko2State:
    result = "A_wins" if reward > REWARD_WIN_THRESHOLD else "B_wins" if reward < -REWARD_WIN_THRESHOLD else "draw"
    virtual_opponent = Glicko2State(rating=1200, rd=50, volatility=0.06)
    current = Glicko2State(
        rating=hypothesis.elo_rating,
        rd=hypothesis.rating_deviation,
        volatility=hypothesis.volatility,
        matches_played=hypothesis.matches_played,
        wins=hypothesis.wins,
        losses=hypothesis.losses,
        draws=hypothesis.draws,
    )
    new_state, _ = compute_glicko2_update(current, virtual_opponent, result)
    return new_state


def apply_feedback_to_registry(registry: HypothesisRegistry, feedbacks: list[ExperimentalFeedback]) -> int:
    applied = 0
    for feedback in feedbacks:
        hypothesis = registry.hypotheses.get(feedback.hypothesis_id)
        if hypothesis is None:
            continue
        updated = apply_feedback_as_glicko2_match(hypothesis, feedback.computed_reward)
        registry.update_rating(
            hypothesis.hypothesis_id,
            updated.rating,
            rating_deviation=updated.rd,
            volatility=updated.volatility,
            matches_played=updated.matches_played,
            wins=updated.wins,
            losses=updated.losses,
            draws=updated.draws,
        )
        applied += 1
    return applied


def extract_keywords(text: str) -> list[str]:
    words = [
        word
        for word in re.sub(r"[^a-zA-Z0-9_\s-]", " ", text.lower()).split()
        if len(word) >= 4 and word not in STOP_WORDS
    ]
    seen: list[str] = []
    for word in words:
        if word not in seen:
            seen.append(word)
    return seen[:20]


def load_reward_memory(path: Path) -> list[RewardMemoryRecord]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    payload = read_json(path)
    rows = payload if isinstance(payload, list) else payload.get("reward_memory", [])
    return [RewardMemoryRecord(**row) for row in rows]


def write_reward_memory(path: Path, records: list[RewardMemoryRecord]) -> None:
    unique: dict[str, RewardMemoryRecord] = {record.memory_id: record for record in records}
    write_json(path, [record.model_dump(mode="json") for record in unique.values()])


def promote_feedback_to_reward_memory(
    feedbacks: list[ExperimentalFeedback],
    registry: HypothesisRegistry,
    existing: list[RewardMemoryRecord],
) -> list[RewardMemoryRecord]:
    records = list(existing)
    known = {record.memory_id for record in records}
    for feedback in feedbacks:
        if abs(feedback.computed_reward) <= STRONG_SIGNAL_THRESHOLD:
            continue
        hypothesis = registry.hypotheses.get(feedback.hypothesis_id)
        if hypothesis is None:
            continue
        memory_id = stable_id("reward_memory", feedback.feedback_id, feedback.hypothesis_id)
        if memory_id in known:
            continue
        records.append(
            RewardMemoryRecord(
                memory_id=memory_id,
                hypothesis_id=hypothesis.hypothesis_id,
                session_id=feedback.session_id or hypothesis.session_id,
                feedback_summary=feedback.feedback_text[:200],
                mechanistic_keywords=extract_keywords(feedback.feedback_text),
                computed_reward=feedback.computed_reward,
                hypothesis_title=hypothesis.title,
                hypothesis_summary=hypothesis.summary,
                created_at=feedback.created_at,
            )
        )
        known.add(memory_id)
    return records


def build_rlef_injection_block(feedbacks: list[ExperimentalFeedback]) -> str:
    validated = [item for item in feedbacks if item.computed_reward > STRONG_SIGNAL_THRESHOLD]
    refuted = [item for item in feedbacks if item.computed_reward < -STRONG_SIGNAL_THRESHOLD]
    if not validated and not refuted:
        return ""
    lines = ["", "## EXPERIMENTAL FEEDBACK (Reinforcement Signal)"]
    if validated:
        lines.extend(["", "### VALIDATED HYPOTHESES:"])
        for item in validated:
            lines.append(f"- Hypothesis {item.hypothesis_id[:8]}: {item.feedback_text[:120]} (reward: +{item.computed_reward:.2f})")
            lines.append(f"  Mechanistic insight: {_extract_insight(item.feedback_text)}")
    if refuted:
        lines.extend(["", "### REFUTED HYPOTHESES:"])
        for item in refuted:
            lines.append(f"- Hypothesis {item.hypothesis_id[:8]}: {item.feedback_text[:120]} (reward: {item.computed_reward:.2f})")
            lines.append("  Avoid similar approaches")
    return "\n".join(lines)


def retrieve_relevant_priors(
    records: list[RewardMemoryRecord],
    query: str,
    *,
    top_k: int = 5,
    embedding_config: dict[str, Any] | None = None,
) -> list[RewardMemoryRecord]:
    strong = [record for record in records if abs(record.computed_reward) > STRONG_SIGNAL_THRESHOLD]
    if not strong or not query:
        return []
    if embedding_config and bool(embedding_config.get("enabled", False)):
        client = LocalMiniLMEmbeddingClient(str(embedding_config.get("model", "sentence-transformers/all-MiniLM-L6-v2")))
        query_vec = client.embed([query])[0]
        texts = [f"{record.hypothesis_title}. {record.hypothesis_summary}. {record.feedback_summary}" for record in strong]
        vectors = client.embed(texts)
        scored = [(dense_cosine(query_vec, vector), record) for vector, record in zip(vectors, strong)]
    else:
        query_terms = set(extract_keywords(query))
        scored = [
            (len(query_terms & set(record.mechanistic_keywords)) + (abs(record.computed_reward) * 0.01), record)
            for record in strong
        ]
    return [record for score, record in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0][:top_k]


def build_prior_block(records: list[RewardMemoryRecord]) -> str:
    if not records:
        return ""
    lines = ["", "## RELEVANT PRIOR EXPERIMENTAL FEEDBACK (Cross-Session Memory)"]
    for record in records:
        sign = f"+{record.computed_reward:.2f}" if record.computed_reward >= 0 else f"{record.computed_reward:.2f}"
        lines.append(f"- [reward: {sign}] {record.feedback_summary}")
        if record.mechanistic_keywords:
            lines.append(f"  Keywords: {', '.join(record.mechanistic_keywords[:8])}")
    return "\n".join(lines)


def _extract_insight(text: str) -> str:
    sentences = [part.strip() for part in re.split(r"[.!?]+", text) if part.strip()]
    keywords = ["mechanism", "pathway", "inhibit", "activat", "reduc", "increas", "express", "regulat"]
    for sentence in sentences:
        if any(keyword in sentence.lower() for keyword in keywords):
            return sentence[:120]
    return (sentences[0] if sentences else text)[:120]
