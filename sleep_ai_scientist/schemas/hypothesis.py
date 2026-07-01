from __future__ import annotations

from enum import Enum
from typing import Literal

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class HypothesisStatus(str, Enum):
    generated = "generated"
    screened = "screened"
    prioritized = "prioritized"
    planned = "planned"
    locked = "locked"
    tested = "tested"
    critic_reviewed = "critic_reviewed"
    accepted = "accepted"
    revised = "revised"
    rejected = "rejected"
    hold = "hold"


class EvidenceLevel(str, Enum):
    confirmatory = "confirmatory"
    exploratory = "exploratory"
    posthoc_exploratory = "posthoc_exploratory"
    speculative = "speculative"


class HypothesisVariables(BaseModel):
    independent: list[str] = Field(default_factory=list)
    dependent: list[str] = Field(default_factory=list)
    covariates: list[str] = Field(default_factory=list)


class HypothesisRecord(BaseModel):
    hypothesis_id: str
    title: str
    mechanism: str
    primary_prediction: str
    secondary_predictions: list[str] = Field(default_factory=list)
    variables: HypothesisVariables
    required_modalities: list[str] = Field(default_factory=list)
    analysis_models: list[str] = Field(default_factory=list)
    expected_direction: dict[str, str] = Field(default_factory=dict)
    falsification_criteria: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    evidence_level: EvidenceLevel = EvidenceLevel.exploratory
    status: HypothesisStatus = HypothesisStatus.generated
    source: str = "rule_based_scientific_loop"
    parent_id: str | None = None
    pre_analysis_score: float | None = None
    score_components: dict[str, float] = Field(default_factory=dict)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    used_data_features: list[str] = Field(default_factory=list)


class ReflectionReview(BaseModel):
    hypothesis_id: str
    review_id: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    unsupported_variables: list[str] = Field(default_factory=list)
    confound_risks: list[str] = Field(default_factory=list)
    causal_language_risk: bool = False
    alternative_explanations: list[str] = Field(default_factory=list)
    falsifiability_score: float = 0.0
    data_grounding_score: float = 0.0
    evidence_grounding_score: float = 0.0
    novelty_score: float = 0.0
    overall_reflection_score: float = 0.0
    recommendation: Literal["keep", "revise", "reject", "hold"] = "hold"


class RankingPair(BaseModel):
    pair_id: str
    hypothesis_a: str
    hypothesis_b: str
    winner: str | None = None
    reason: str | None = None
    score_a: float | None = None
    score_b: float | None = None


class RankingResult(BaseModel):
    hypothesis_id: str
    elo_score: float = 1500.0
    tournament_wins: int = 0
    tournament_losses: int = 0
    tournament_draws: int = 0
    final_rank: int = 0
    rank_reason: str | None = None


class ProximityCluster(BaseModel):
    cluster_id: str
    hypothesis_ids: list[str] = Field(default_factory=list)
    representative_id: str
    cluster_label: str
    diversity_score: float = 0.0
    similarity_summary: str | None = None


class EvolvedHypothesisRecord(BaseModel):
    hypothesis_id: str
    parent_ids: list[str] = Field(default_factory=list)
    evolution_strategy: Literal["refine", "merge", "mutate"]
    title: str
    mechanism: str
    primary_prediction: str
    variables: HypothesisVariables
    required_modalities: list[str] = Field(default_factory=list)
    falsification_criteria: list[str] = Field(default_factory=list)
    evidence_level: EvidenceLevel = EvidenceLevel.posthoc_exploratory
    source: str = "co_scientist_evolution"
    evolution_rationale: str
    status: HypothesisStatus = HypothesisStatus.generated


class MetaReview(BaseModel):
    review_id: str
    top_hypotheses: list[str] = Field(default_factory=list)
    rejected_hypotheses: list[str] = Field(default_factory=list)
    revised_hypotheses: list[str] = Field(default_factory=list)
    major_themes: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    recommended_next_experiments: list[dict] = Field(default_factory=list)
    summary: str
