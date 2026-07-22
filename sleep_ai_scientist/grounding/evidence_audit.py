from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_csv, write_json
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _median(values: list[float]) -> float:
    return round(float(statistics.median(values)), 3) if values else 0.0


def build_evidence_audit(
    papers: list[LiteratureRecord],
    evidence: list[EvidenceRecord],
    preferred_mechanisms: list[str],
    llm_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    by_paper = Counter(item.paper_id for item in evidence)
    papers_with_evidence = set(by_paper)
    citation_values = [float(item.citation_count or 0) for item in evidence if item.citation_count is not None]
    audit = {
        "total_papers": len(papers),
        "papers_with_evidence": len(papers_with_evidence),
        "papers_without_evidence": len(papers) - len(papers_with_evidence),
        "evidence_count": len(evidence),
        "evidence_per_paper_mean": _mean([float(count) for count in by_paper.values()]),
        "evidence_per_paper_median": _median([float(count) for count in by_paper.values()]),
        "mechanism_counts": dict(Counter(item.mechanism for item in evidence)),
        "modality_counts": dict(Counter(item.modality for item in evidence)),
        "direction_counts": dict(Counter(item.direction.value for item in evidence)),
        "evidence_type_counts": dict(Counter(item.evidence_type.value for item in evidence)),
        "species_counts": dict(Counter(item.species or "unknown" for item in evidence)),
        "evidence_context_counts": dict(Counter(item.evidence_context or "unknown" for item in evidence)),
        "downstream_role_counts": dict(Counter(item.downstream_role or "unknown" for item in evidence)),
        "human_evidence_count": sum(1 for item in evidence if item.species == "human"),
        "animal_evidence_count": sum(1 for item in evidence if item.species in {"mouse", "rat", "cat", "nonhuman_primate", "animal", "mixed"}),
        "translational_evidence_count": sum(1 for item in evidence if item.downstream_role == "translational_mechanistic_support"),
        "citation_availability_rate": round(sum(1 for item in evidence if item.citation_count is not None) / len(evidence), 3) if evidence else 0.0,
        "journal_availability_rate": round(sum(1 for item in evidence if item.journal) / len(evidence), 3) if evidence else 0.0,
        "median_citation_count": _median(citation_values),
        "mean_extraction_confidence_score": _mean([item.extraction_confidence_score or 0.0 for item in evidence]),
        "mean_evidence_quality_score": _mean([item.evidence_quality_score or 0.0 for item in evidence]),
        "mean_mechanistic_strength_score": _mean([item.mechanistic_strength_score or 0.0 for item in evidence]),
        "mean_clinical_applicability_score": _mean([item.clinical_applicability_score or 0.0 for item in evidence]),
        "mean_evidence_feasibility_score": _mean([item.evidence_feasibility_score or 0.0 for item in evidence]),
        "mean_final_evidence_score": _mean([item.final_evidence_score or 0.0 for item in evidence]),
        "missing_population_rate": round(sum(1 for item in evidence if not item.population) / len(evidence), 3) if evidence else 0.0,
        "missing_modality_rate": round(sum(1 for item in evidence if not item.modality) / len(evidence), 3) if evidence else 0.0,
        "missing_variable_rate": round(sum(1 for item in evidence if not item.variable_or_feature) / len(evidence), 3) if evidence else 0.0,
        "unclear_direction_rate": round(sum(1 for item in evidence if item.direction == EvidenceDirection.unclear) / len(evidence), 3) if evidence else 0.0,
        "possible_positive_evidence_bias": not any(item.direction in {EvidenceDirection.refute, EvidenceDirection.null} for item in evidence),
        "mechanisms_with_zero_evidence": [mechanism for mechanism in preferred_mechanisms if mechanism not in {item.mechanism for item in evidence}],
        "top_unmatched_relevant_papers": [paper.paper_id for paper in papers if paper.paper_id not in papers_with_evidence][:20],
    }
    audit.update(
        {
            "llm_enabled": bool((llm_stats or {}).get("enabled", False)),
            "llm_calls_attempted": int((llm_stats or {}).get("calls_attempted", 0)),
            "llm_calls_succeeded": int((llm_stats or {}).get("calls_succeeded", 0)),
            "llm_calls_failed": int((llm_stats or {}).get("calls_failed", 0)),
            "llm_revised_evidence_count": int((llm_stats or {}).get("revised_evidence_count", 0)),
            "llm_split_claim_count": int((llm_stats or {}).get("split_claim_count", 0)),
            "llm_excluded_claim_count": int((llm_stats or {}).get("excluded_claim_count", 0)),
        }
    )
    return audit


def write_evidence_audit(out_dir: Path, audit: dict[str, Any], papers: list[LiteratureRecord], evidence: list[EvidenceRecord]) -> None:
    write_json(out_dir / "evidence_extraction_audit.json", audit)
    matched = {item.paper_id for item in evidence}
    unmatched = [{"paper_id": paper.paper_id, "title": paper.title, "source": paper.source} for paper in papers if paper.paper_id not in matched]
    write_csv(out_dir / "unmatched_relevant_papers.csv", unmatched)
    mechanism_rows = [{"mechanism": key, "evidence_count": value} for key, value in sorted(audit.get("mechanism_counts", {}).items())]
    write_csv(out_dir / "mechanism_coverage_summary.csv", mechanism_rows)
