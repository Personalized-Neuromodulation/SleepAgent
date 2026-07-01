from __future__ import annotations

from enum import Enum

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class EvidenceDirection(str, Enum):
    support = "support"
    refute = "refute"
    null = "null"
    unclear = "unclear"


class EvidenceType(str, Enum):
    meta_analysis = "meta_analysis"
    systematic_review = "systematic_review"
    review = "review"
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
    source_text: str | None = None
    section: str | None = None
    sentence_index: int | None = None
    matched_terms: list[str] = Field(default_factory=list)
    extraction_method: str = "rule"
    query_source: str | None = None
    provider: str | None = None
    doi: str | None = None
    pmid: str | None = None
    journal: str | None = None
    publication_year: int | None = None
    publication_type: str | None = None
    citation_count: int | None = None
    citation_source: str | None = None
    citation_count_age_normalized: float | None = None
    journal_impact_factor: float | None = None
    journal_impact_factor_year: int | None = None
    journal_quartile: str | None = None
    journal_metric_source: str | None = None
    is_open_access: bool | None = None
    condition: str | None = None
    comparison_group: str | None = None
    effect_direction: str | None = "unknown"
    study_design: str | None = "unknown"
    study_design_detail: str | None = "unknown"
    sample_size_total: int | None = None
    sample_size_insomnia: int | None = None
    sample_size_control: int | None = None
    sample_size_note: str | None = None
    species: str | None = "unknown"
    statistical_test: str | None = None
    effect_size: float | None = None
    effect_size_type: str | None = None
    p_value: float | None = None
    corrected_p_value: float | None = None
    multiple_comparison_correction: str | None = None
    confidence_interval: list[float] | None = None
    statistical_note: str | None = None
    limitations: list[str] = Field(default_factory=list)
    confounds: list[str] = Field(default_factory=list)
    causal_inference_limit: bool = True
    overclaim_risk: float | None = None
    model_system: str | None = "unknown"
    evidence_context: str | None = "unknown"
    translational_relevance: str | None = "unknown"
    translational_risk: list[str] = Field(default_factory=list)
    downstream_role: str | None = None
    data_mappability_hint: str | None = "unclear"
    mapping_status: str | None = "not_checked"
    mapped_data_features: list[str] = Field(default_factory=list)
    mechanism_in_scope: bool = True
    population_match_score: float | None = None
    modality_match_score: float | None = None
    hypothesis_relevance_score: float | None = None
    extraction_confidence_score: float | None = None
    mechanistic_strength_score: float | None = None
    clinical_applicability_score: float | None = None
    evidence_feasibility_score: float | None = None
    final_evidence_score: float | None = None
    confidence_reason: str | None = None
    llm_verified: bool = False
    llm_revision_applied: bool = False
    llm_warnings: list[str] = Field(default_factory=list)
