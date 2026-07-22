from __future__ import annotations

from typing import Any

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.schemas.data_profile import DataProfile, MappingStatus, VariableMappingRecord
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def run_grounding_qc(
    literature: list[LiteratureRecord],
    evidence: list[EvidenceRecord],
    mappings: list[VariableMappingRecord],
    analysis_ready: DataProfile,
    preferred_mechanisms: list[str],
) -> dict[str, Any]:
    ready_features = {feature.feature_name for feature in analysis_ready.features}
    approved = sorted({feature for mapping in mappings for feature in mapping.approved_data_features})
    hallucinated = [feature for feature in approved if feature not in ready_features]
    evidence_mechanisms = {item.mechanism for item in evidence}
    gaps = [mechanism for mechanism in preferred_mechanisms if mechanism not in evidence_mechanisms]
    unavailable = [mapping.concept for mapping in mappings if mapping.mapping_status == MappingStatus.unavailable]
    warnings: list[str] = []
    errors: list[str] = []
    recommended_next_steps: list[str] = []

    if len(literature) < 100:
        warnings.append("final literature count below 100")
        recommended_next_steps.append("Review query coverage or API availability before using this corpus for benchmark work.")
    if len(evidence) < 50:
        warnings.append("evidence count below 50")
        recommended_next_steps.append("Inspect extraction rules and online literature coverage.")
    if gaps:
        warnings.append("preferred mechanism coverage gaps detected")
        recommended_next_steps.append("Add targeted online queries for mechanisms listed in check_mechanism_coverage.gaps.")
    if not any(item.direction in {EvidenceDirection.refute, EvidenceDirection.null} for item in evidence):
        warnings.append("possible positive evidence bias")
        recommended_next_steps.append("Review query set and extraction rules for null/refuting findings.")
    if hallucinated:
        errors.append("approved_variables_from_grounding contains variables absent from analysis_ready_profile")
        recommended_next_steps.append("Remove hallucinated approved variables or add real Foundation-approved features before proceeding.")

    report = {
        "warnings": warnings,
        "errors": errors,
        "recommended_next_steps": recommended_next_steps,
        "checks": {
            "check_min_literature_count": {"passed": len(literature) >= 100, "count": len(literature), "warning": "" if len(literature) >= 100 else "final literature count below 100"},
            "check_evidence_count": {"passed": len(evidence) >= 50, "count": len(evidence), "warning": "" if len(evidence) >= 50 else "evidence count below 50"},
            "check_mechanism_coverage": {"passed": not gaps, "gaps": gaps},
            "check_variable_mapping": {"passed": bool(approved) and bool(unavailable or mappings), "mapped_concepts": sum(1 for item in mappings if item.mapping_status == MappingStatus.mapped), "unavailable_concepts": unavailable},
            "check_no_hallucinated_variables": {"passed": not hallucinated, "hallucinated_variables": hallucinated},
            "check_refute_and_null_present": {
                "passed": any(item.direction in {EvidenceDirection.refute, EvidenceDirection.null} for item in evidence),
                "warning": "" if any(item.direction in {EvidenceDirection.refute, EvidenceDirection.null} for item in evidence) else "possible positive evidence bias",
            },
        }
    }
    report["passed"] = not errors and all(item.get("passed", False) for item in report["checks"].values())
    return report


def write_grounding_qc_report(path, report: dict[str, Any]) -> None:
    write_json(path, report)
