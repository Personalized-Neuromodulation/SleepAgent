from __future__ import annotations

from enum import Enum
from typing import Any

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class ExperimentPlanStatus(str, Enum):
    draft = "draft"
    locked = "locked"
    executed = "executed"
    failed = "failed"


class ExperimentPlan(BaseModel):
    experiment_id: str
    hypothesis_id: str
    analysis_type: str
    outcome: str
    predictors: list[str] = Field(default_factory=list)
    covariates: list[str] = Field(default_factory=list)
    group_variable: str | None = None
    model_formula: str
    quality_gates: dict[str, int | float | str | list[Any]] = Field(default_factory=dict)
    correction_method: str = "fdr_bh"
    robustness: list[str] = Field(default_factory=list)
    lock_status: ExperimentPlanStatus = ExperimentPlanStatus.draft
    created_at: str
    locked_at: str | None = None
    plan_hash: str | None = None
