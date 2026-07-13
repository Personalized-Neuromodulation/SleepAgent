from __future__ import annotations

from typing import Any

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class FeatureTable(BaseModel):
    modality: str
    path: str
    subject_id_column: str = "subject_id"
    feature_columns: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureExtractionResult(BaseModel):
    plan_id: str
    output_dir: str
    tables: list[FeatureTable] = Field(default_factory=list)
    profile_path: str = ""
    merged_features_path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
