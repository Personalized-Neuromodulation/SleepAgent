from __future__ import annotations

from enum import Enum
from typing import Any

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class ExperimentVariableRole(str, Enum):
    predictor = "predictor"
    outcome = "outcome"
    covariate = "covariate"
    negative_control = "negative_control"


class ExperimentVariable(BaseModel):
    name: str
    role: ExperimentVariableRole
    scientific_concept: str = ""
    modality: str = ""
    source_file: str = ""
    source_column: str = ""
    approved: bool = False
    missing_rate: float | None = None
    n_available: int | None = None
    mapping_confidence: float = 0.0
    notes: str = ""


class ExperimentPlan(BaseModel):
    plan_id: str
    hypothesis_id: str
    hypothesis_title: str
    scientific_question: str
    hypothesis_summary: str = ""
    hypothesis_content: str = ""
    predictors: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    covariates: list[str] = Field(default_factory=list)
    negative_controls: list[str] = Field(default_factory=list)
    variables: list[ExperimentVariable] = Field(default_factory=list)
    primary_tests: list[dict[str, Any]] = Field(default_factory=list)
    analysis_plan: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class StatisticalTestResult(BaseModel):
    test_id: str
    predictor: str
    outcome: str
    method: str
    n: int = 0
    effect: float | None = None
    p_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    direction: str = ""
    passed: bool = False
    notes: str = ""


class StatsAgentResult(BaseModel):
    plan_id: str
    hypothesis_id: str
    tests: list[StatisticalTestResult] = Field(default_factory=list)
    summary: str = ""


class RobustnessCheckResult(BaseModel):
    check_id: str
    target_test_id: str
    method: str
    n_iterations: int = 0
    original_effect: float | None = None
    median_effect: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    sign_stability: float | None = None
    passed: bool = False
    notes: str = ""


class NegativeControlResult(BaseModel):
    control_id: str
    control_type: str
    predictor: str
    outcome: str
    n: int = 0
    effect: float | None = None
    passed: bool = False
    notes: str = ""


class MLAgentResult(BaseModel):
    plan_id: str
    hypothesis_id: str
    outcome: str = ""
    features: list[str] = Field(default_factory=list)
    n: int = 0
    model_type: str = ""
    cv_folds: int = 0
    score_name: str = ""
    score_mean: float | None = None
    score_std: float | None = None
    feature_importance: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class CriticFinding(BaseModel):
    severity: str = "medium"
    category: str = "scientific_review"
    message: str = ""
    recommendation: str = ""


class ExperimentResultBundle(BaseModel):
    plan: ExperimentPlan
    stats_result: StatsAgentResult | None = None
    ml_result: MLAgentResult | None = None
    robustness_results: list[RobustnessCheckResult] = Field(default_factory=list)
    negative_control_results: list[NegativeControlResult] = Field(default_factory=list)
    critic_findings: list[CriticFinding] = Field(default_factory=list)
    evidence_update: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
