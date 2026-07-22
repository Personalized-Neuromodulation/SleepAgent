from __future__ import annotations

from statistics import mean

from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord, EvidenceType


TYPE_WEIGHTS = {
    EvidenceType.meta_analysis: 0.95,
    EvidenceType.systematic_review: 0.9,
    EvidenceType.review: 0.72,
    EvidenceType.empirical: 0.78,
    EvidenceType.method: 0.55,
    EvidenceType.case: 0.35,
    EvidenceType.unknown: 0.25,
}


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _citation_journal_aux(record: EvidenceRecord) -> float:
    citation = min(0.7, (record.citation_count_age_normalized or 0.0) / 100.0)
    journal = 0.0
    if record.journal_impact_factor is not None:
        journal = min(0.3, float(record.journal_impact_factor) / 100.0)
    elif record.journal_quartile:
        journal = {"Q1": 0.25, "Q2": 0.15, "Q3": 0.08, "Q4": 0.03}.get(str(record.journal_quartile).upper(), 0.0)
    return _clamp(citation + journal)


def score_extraction_confidence(record: EvidenceRecord) -> float:
    score = record.extraction_confidence_score if record.extraction_confidence_score is not None else record.confidence_score
    score = score or 0.3
    score += 0.08 if record.source_text else -0.2
    score += min(0.12, len(record.matched_terms) * 0.02)
    score += 0.06 if record.mechanism else -0.1
    score += 0.06 if record.direction != EvidenceDirection.unclear else -0.08
    score += 0.04 if record.variable_or_feature else -0.05
    if record.llm_verified:
        score += 0.05
    if record.llm_warnings:
        score -= 0.08
    return _clamp(score)


def score_evidence_quality(record: EvidenceRecord) -> float:
    score = TYPE_WEIGHTS.get(record.evidence_type, 0.25)
    score += 0.08 if record.study_design in {"randomized", "longitudinal", "cohort"} else 0.0
    score += 0.04 if record.sample_size_total and record.sample_size_total >= 50 else 0.0
    score += 0.05 if record.direction != EvidenceDirection.unclear else -0.06
    score -= min(0.18, len(record.limitations) * 0.04 + len(record.confounds) * 0.03)
    score += 0.08 * _citation_journal_aux(record)
    return _clamp(score)


def score_mechanistic_strength(record: EvidenceRecord) -> float:
    score = 0.25
    if record.mechanism:
        score += 0.18
    if record.study_design_detail in {"optogenetic_causal_manipulation", "chemogenetic_causal_manipulation"}:
        score += 0.32
    if record.model_system in {"electrophysiology", "calcium_imaging", "optogenetic_model"}:
        score += 0.18
    if record.evidence_context == "animal_mechanistic":
        score += 0.12
    if any(term in (record.source_text or "").lower() for term in ["sleep stage", "nrem", "rem", "spindle", "slow wave"]):
        score += 0.08
    if record.direction == EvidenceDirection.unclear:
        score -= 0.1
    return _clamp(score)


def score_clinical_applicability(record: EvidenceRecord) -> float:
    population = (record.population or "").lower()
    context = record.evidence_context or "unknown"
    model = record.model_system or "unknown"
    if "insomnia" in population and record.species == "human":
        return 1.0
    if "poor sleeper" in population or "sleep complaint" in population:
        return 0.8
    if context == "human_neuroimaging":
        return 0.75
    if context == "human_general_sleep":
        return 0.6
    if model in {"sleep_deprivation_model", "insomnia_like_model"}:
        return 0.5
    if context == "animal_mechanistic":
        return 0.4
    if context == "cellular_molecular":
        return 0.2
    return 0.1


def score_feasibility(record: EvidenceRecord) -> float:
    score = 0.15
    score += 0.2 if record.mechanism_in_scope else -0.05
    score += 0.25 if record.data_mappability_hint == "mapped_candidate" else -0.1 if record.data_mappability_hint == "theory_only" else 0.0
    score += record.modality_match_score if record.modality_match_score is not None else (0.15 if record.modality else 0.0)
    score += record.population_match_score if record.population_match_score is not None else (0.12 if (record.population or "").lower() in {"insomnia", "human"} else 0.04)
    score += 0.1 if record.direction in {EvidenceDirection.support, EvidenceDirection.refute, EvidenceDirection.null} else -0.08
    score += 0.08 if record.confounds else 0.0
    if record.downstream_role in {"critique_only", "not_for_hypothesis_generation"}:
        score = min(score, 0.35)
    return _clamp(score)


def grade_evidence(record: EvidenceRecord) -> EvidenceRecord:
    record.extraction_confidence_score = score_extraction_confidence(record)
    record.evidence_quality_score = score_evidence_quality(record)
    record.mechanistic_strength_score = score_mechanistic_strength(record)
    record.clinical_applicability_score = score_clinical_applicability(record)
    record.evidence_feasibility_score = score_feasibility(record)
    aux = _citation_journal_aux(record)
    record.final_evidence_score = _clamp(
        0.20 * (record.extraction_confidence_score or 0.0)
        + 0.25 * (record.evidence_quality_score or 0.0)
        + 0.20 * (record.mechanistic_strength_score or 0.0)
        + 0.20 * (record.evidence_feasibility_score or 0.0)
        + 0.10 * (record.clinical_applicability_score or 0.0)
        + 0.05 * aux
    )
    record.confidence_score = record.extraction_confidence_score or record.confidence_score
    return record


def grade_evidence_records(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    return [grade_evidence(record) for record in records]


def evidence_quality_summary(records: list[EvidenceRecord]) -> dict:
    quality_scores = [record.evidence_quality_score or 0.0 for record in records]
    final_scores = [record.final_evidence_score or 0.0 for record in records]
    return {
        "evidence_count": len(records),
        "support_count": sum(1 for record in records if record.direction == EvidenceDirection.support),
        "refute_count": sum(1 for record in records if record.direction == EvidenceDirection.refute),
        "null_count": sum(1 for record in records if record.direction == EvidenceDirection.null),
        "unclear_count": sum(1 for record in records if record.direction == EvidenceDirection.unclear),
        "mean_evidence_quality_score": round(mean(quality_scores), 3) if quality_scores else 0.0,
        "mean_final_evidence_score": round(mean(final_scores), 3) if final_scores else 0.0,
        "high_quality_evidence_count": sum(1 for score in quality_scores if score >= 0.75),
        "low_quality_evidence_count": sum(1 for score in quality_scores if score < 0.40),
        "high_feasibility_evidence_count": sum(1 for record in records if (record.evidence_feasibility_score or 0.0) >= 0.75),
    }
