from __future__ import annotations

from typing import Any, Literal

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class AnalysisResult(BaseModel):
    experiment_id: str
    hypothesis_id: str
    model_formula: str
    n_total: int
    n_used: int
    coefficients: dict[str, float] = Field(default_factory=dict)
    p_values: dict[str, float] = Field(default_factory=dict)
    corrected_p_values: dict[str, float] = Field(default_factory=dict)
    effect_sizes: dict[str, float] = Field(default_factory=dict)
    confidence_intervals: dict[str, list[float]] = Field(default_factory=dict)
    model_fit: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    status: str = "ok"


class RobustnessResult(BaseModel):
    experiment_id: str
    bootstrap_summary: dict[str, Any] | None = None
    permutation_summary: dict[str, Any] | None = None
    sensitivity_summary: dict[str, Any] | None = None
    passed: bool = False
    warnings: list[str] = Field(default_factory=list)


class CriticReview(BaseModel):
    experiment_id: str
    hypothesis_id: str
    decision: Literal["accepted", "revised", "rejected", "hold", "exploratory_only"]
    evidence_strength: Literal["weak", "moderate", "strong"]
    claim_strength: Literal[
        "not_supported", "exploratory_association", "robust_association", "replicated_association"
    ]
    main_concerns: list[str] = Field(default_factory=list)
    required_followups: list[str] = Field(default_factory=list)
    causal_language_allowed: bool = False
    summary: str
