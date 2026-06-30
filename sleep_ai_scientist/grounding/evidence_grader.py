from __future__ import annotations

from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord, EvidenceType


TYPE_WEIGHTS = {
    EvidenceType.meta_analysis: 0.9,
    EvidenceType.review: 0.75,
    EvidenceType.empirical: 0.8,
    EvidenceType.method: 0.6,
    EvidenceType.case: 0.35,
    EvidenceType.unknown: 0.25,
}


def grade_evidence(record: EvidenceRecord) -> EvidenceRecord:
    """Assign a non-uniform quality score from evidence type and completeness."""
    score = TYPE_WEIGHTS.get(record.evidence_type, 0.25)
    score += 0.03 if record.population else -0.03
    score += 0.04 if record.modality else -0.04
    score += 0.04 if record.variable_or_feature else -0.04
    score += 0.04 if record.direction != EvidenceDirection.unclear else -0.04
    score += 0.03 if record.limitation else 0.0
    record.evidence_quality_score = round(max(0.0, min(1.0, score)), 3)
    return record


def grade_evidence_records(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    """Grade evidence records in place and return them for pipeline chaining."""
    return [grade_evidence(record) for record in records]
