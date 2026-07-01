from __future__ import annotations

from typing import Literal

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class HypothesisQualityScore(BaseModel):
    hypothesis_id: str
    valid_variables: bool
    has_supporting_evidence: bool
    has_falsification_criteria: bool
    has_analysis_model: bool
    evidence_level: str
    status: str
    mechanism_plausibility_score: float
    data_testability_score: float
    evidence_grounding_score: float
    falsifiability_score: float
    novelty_proxy_score: float
    clinical_value_score: float
    overclaim_risk_score: float
    overall_quality_score: float
    warnings: list[str] = Field(default_factory=list)


class GroundingBenchmarkScore(BaseModel):
    hypothesis_id: str
    used_variables: list[str] = Field(default_factory=list)
    missing_variables: list[str] = Field(default_factory=list)
    mapped_concepts: list[str] = Field(default_factory=list)
    unavailable_concepts: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    data_grounding_score: float
    evidence_grounding_score: float
    grounding_passed: bool
    warnings: list[str] = Field(default_factory=list)


class ExecutionBenchmarkScore(BaseModel):
    experiment_id: str
    hypothesis_id: str
    has_locked_plan: bool
    plan_file_exists: bool
    result_file_exists: bool
    robustness_file_exists: bool
    critic_review_exists: bool
    n_used: int | None = None
    model_formula: str | None = None
    execution_success: bool
    execution_score: float
    warnings: list[str] = Field(default_factory=list)


class CriticBenchmarkScore(BaseModel):
    experiment_id: str
    hypothesis_id: str
    critic_decision: str
    expert_decision: str | None = None
    agreement: bool | None = None
    agreement_score: float | None = None
    critic_claim_strength: str | None = None
    expert_claim_strength: str | None = None
    overclaim_detected: bool = False
    critic_score: float
    warnings: list[str] = Field(default_factory=list)


class CoScientistBenchmarkScore(BaseModel):
    hypothesis_id: str
    in_scientific_loop_top_k: bool
    in_co_scientist_top_k: bool
    ranking_score: float | None = None
    reflection_score: float | None = None
    cluster_id: str | None = None
    evolved: bool = False
    parent_ids: list[str] = Field(default_factory=list)
    diversity_contribution_score: float
    improvement_over_scientific_loop_score: float
    co_scientist_score: float
    warnings: list[str] = Field(default_factory=list)


class ReproducibilityScore(BaseModel):
    artifact_id: str
    artifact_type: str
    required_files: list[str] = Field(default_factory=list)
    existing_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    has_config: bool = False
    has_schema: bool = False
    has_report: bool = False
    has_audit_trace: bool = False
    reproducibility_score: float
    warnings: list[str] = Field(default_factory=list)


class ExpertRating(BaseModel):
    expert_id: str
    item_type: Literal["hypothesis", "critic_review", "experiment_plan", "meta_review"]
    item_id: str
    mechanism_plausibility: int | None = None
    data_testability: int | None = None
    evidence_grounding: int | None = None
    novelty: int | None = None
    clinical_value: int | None = None
    statistical_feasibility: int | None = None
    confound_risk: int | None = None
    overclaim_risk: int | None = None
    priority_for_analysis: int | None = None
    decision: Literal["accept", "revise", "reject", "hold", "exploratory_only"] | None = None
    free_text_comment: str | None = None


class PairwisePreference(BaseModel):
    pair_id: str
    expert_id: str | None = None
    item_type: Literal["hypothesis", "critic_review", "experiment_plan"]
    item_a: str
    item_b: str
    preferred_item: str | None = None
    preference_strength: int | None = None
    reason: str | None = None
    source: Literal["expert", "synthetic", "rule_based"] = "rule_based"


class BenchmarkSummary(BaseModel):
    total_hypotheses: int
    valid_hypothesis_rate: float
    data_grounding_rate: float
    executable_plan_rate: float
    critic_expert_agreement: float | None = None
    mean_hypothesis_quality_score: float
    mean_reproducibility_score: float
    co_scientist_improvement_score: float | None = None
    passed: bool
    failed_checks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
