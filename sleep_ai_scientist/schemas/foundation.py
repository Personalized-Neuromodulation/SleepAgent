from __future__ import annotations

from enum import Enum
from typing import Any

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class FeatureRole(str, Enum):
    feature = "feature"
    outcome = "outcome"
    covariate = "covariate"
    group = "group"
    scale = "scale"
    qc = "qc"


class QCStatus(str, Enum):
    pass_ = "pass"
    caution = "caution"
    fail = "fail"
    unknown = "unknown"


class SubjectRecord(BaseModel):
    subject_id: str
    group: str | None = None
    age: float | None = None
    sex: str | None = None
    available_modalities: list[str] = Field(default_factory=list)
    qc_status: str | None = None
    notes: str | None = None


class FeatureRegistryRecord(BaseModel):
    feature_name: str
    modality: str
    source_file: str
    source_column: str
    role: FeatureRole = FeatureRole.feature
    dtype: str | None = None
    unit: str | None = None
    description: str | None = None
    missing_rate: float | None = None
    n_available: int | None = None
    qc_dependency: list[str] = Field(default_factory=list)
    approved: bool = False
    approval_reason: str | None = None


class QCRecord(BaseModel):
    subject_id: str
    modality: str
    qc_status: QCStatus = QCStatus.unknown
    qc_metric: str | None = None
    qc_value: float | str | None = None
    reason: str | None = None


class DataDictionaryEntry(BaseModel):
    variable: str
    modality: str
    role: str
    description: str | None = None
    unit: str | None = None
    source_file: str | None = None
    source_column: str | None = None
    allowed_values: list[str] | None = None
    valid_range: list[float] | None = None


class ApprovedVariables(BaseModel):
    EEG: list[str] = Field(default_factory=list)
    fMRI: list[str] = Field(default_factory=list)
    DTI: list[str] = Field(default_factory=list)
    MRI: list[str] = Field(default_factory=list)
    scales: list[str] = Field(default_factory=list)
    covariates: list[str] = Field(default_factory=list)
    group: list[str] = Field(default_factory=list)
    qc: list[str] = Field(default_factory=list)
