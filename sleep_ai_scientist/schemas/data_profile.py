from __future__ import annotations

from enum import Enum

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class MappingStatus(str, Enum):
    mapped = "mapped"
    ambiguous = "ambiguous"
    unavailable = "unavailable"


class FeatureProfile(BaseModel):
    feature_name: str
    modality: str = ""
    source_file: str = ""
    source_column: str = ""
    missing_rate: float | None = None
    n_available: int | None = None
    qc_status: str = ""
    approved: bool = False
    role: str = "feature"


class DataProfile(BaseModel):
    profile_type: str
    features: list[FeatureProfile] = Field(default_factory=list)


class VariableMappingRecord(BaseModel):
    concept: str
    candidate_variables: list[str] = Field(default_factory=list)
    approved_data_features: list[str] = Field(default_factory=list)
    modality: str = ""
    mapping_confidence: float = 0.0
    mapping_status: MappingStatus = MappingStatus.unavailable
