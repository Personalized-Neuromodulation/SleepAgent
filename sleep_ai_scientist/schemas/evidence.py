from __future__ import annotations

from enum import Enum

from sleep_ai_scientist.common.pydantic_compat import BaseModel


class EvidenceDirection(str, Enum):
    support = "support"
    refute = "refute"
    null = "null"
    unclear = "unclear"


class EvidenceType(str, Enum):
    review = "review"
    meta_analysis = "meta_analysis"
    empirical = "empirical"
    method = "method"
    case = "case"
    unknown = "unknown"


class EvidenceRecord(BaseModel):
    evidence_id: str
    paper_id: str
    claim: str
    population: str = ""
    modality: str = ""
    variable_or_feature: str = ""
    mechanism: str = ""
    direction: EvidenceDirection = EvidenceDirection.unclear
    evidence_type: EvidenceType = EvidenceType.unknown
    limitation: str = ""
    confidence_score: float = 0.5
    evidence_quality_score: float | None = None
