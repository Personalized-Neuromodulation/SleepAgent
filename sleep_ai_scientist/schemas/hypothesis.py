from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HypothesisStatus(str, Enum):
    pending_review = "pending_review"
    reviewing = "reviewing"
    reviewed = "reviewed"
    rejected = "rejected"
    active = "active"
    evolved = "evolved"
    quarantined = "quarantined"


class ReviewType(str, Enum):
    initial = "initial"
    full = "full"
    deep_verification = "deep_verification"
    observation = "observation"
    simulation = "simulation"
    tournament = "tournament"
    expert = "expert"


class ReviewVerdict(str, Enum):
    pass_ = "pass"
    fail = "fail"
    uncertain = "uncertain"


class GenerationStrategy(str, Enum):
    literature_exploration = "literature_exploration"
    scientific_debate = "scientific_debate"
    assumption_chaining = "assumption_chaining"
    research_expansion = "research_expansion"


class Hypothesis(BaseModel):
    hypothesis_id: str
    session_id: str
    title: str
    summary: str
    content: str
    rationale: str
    experimental_plan: str = ""
    novelty_assessment: str = ""
    key_assumptions: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    generation_strategy: str = GenerationStrategy.literature_exploration.value
    generation_round: int = 0
    elo_rating: float = 1200.0
    rating_deviation: float = 350.0
    volatility: float = 0.06
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    status: HypothesisStatus = HypothesisStatus.pending_review
    parent_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class HypothesisReview(BaseModel):
    review_id: str
    hypothesis_id: str
    session_id: str
    review_type: ReviewType
    verdict: ReviewVerdict
    novelty_score: float | None = None
    correctness_score: float | None = None
    testability_score: float | None = None
    safety_flag: bool = False
    summary: str = ""
    critique: str = ""
    supporting_evidence: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class TournamentMatch(BaseModel):
    match_id: str
    session_id: str
    hypothesis_a_id: str
    hypothesis_b_id: str
    result: str
    winner_elo_after: float
    loser_elo_after: float
    rationale: str = ""
    round: int = 0
    created_at: str = Field(default_factory=utc_now_iso)


class ProximityEdge(BaseModel):
    session_id: str
    hypothesis_a_id: str
    hypothesis_b_id: str
    similarity: float


class HypothesisLineageRecord(BaseModel):
    hypothesis_id: str
    parent_ids: list[str] = Field(default_factory=list)
    generation_strategy: str = ""
    generation_round: int = 0
