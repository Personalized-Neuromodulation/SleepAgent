from __future__ import annotations

from pathlib import Path

from sleep_ai_scientist.common.config import config_path
from sleep_ai_scientist.common.io import read_yaml, write_yaml
from sleep_ai_scientist.schemas.data_profile import DataProfile, MappingStatus, VariableMappingRecord
from sleep_ai_scientist.schemas.evidence import EvidenceRecord


def _concepts_from_evidence(evidence: list[EvidenceRecord]) -> list[str]:
    """Preserve first-seen mechanism order for stable mapping output."""
    concepts: list[str] = []
    for item in evidence:
        concept = item.mechanism
        if concept and concept not in concepts:
            concepts.append(concept)
    return concepts


def load_mapping_rules(path: Path) -> dict[str, dict]:
    """Load concept-to-variable rules from YAML config."""
    payload = read_yaml(path)
    return payload.get("mappings", payload)


def map_variables(
    evidence: list[EvidenceRecord],
    analysis_ready: DataProfile,
    rules_path: Path,
) -> list[VariableMappingRecord]:
    """Map literature concepts to real analysis-ready data features.

    This is the main data-constraint gate in Phase 1: candidate variables are
    only accepted when they are present in analysis_ready_profile.
    """
    rules = load_mapping_rules(rules_path)
    ready_names = {item.feature_name for item in analysis_ready.features}
    records: list[VariableMappingRecord] = []
    for concept in _concepts_from_evidence(evidence):
        rule = rules.get(concept, {})
        candidates = [str(item) for item in rule.get("candidates", [])]
        approved = [name for name in candidates if name in ready_names]
        # Multiple approved features are useful but not uniquely resolved yet,
        # so they are marked ambiguous for downstream Phase 2 handling.
        if len(approved) == 1:
            status = MappingStatus.mapped
            confidence = 0.9
        elif len(approved) > 1:
            status = MappingStatus.ambiguous
            confidence = 0.65
        else:
            status = MappingStatus.unavailable
            confidence = 0.0
        records.append(
            VariableMappingRecord(
                concept=concept,
                candidate_variables=candidates,
                approved_data_features=approved,
                modality=str(rule.get("modality", "")),
                mapping_confidence=confidence,
                mapping_status=status,
            )
        )
    return records


def write_mapping_outputs(config: dict, mappings: list[VariableMappingRecord]) -> None:
    """Write detailed mappings and the approved variable subset."""
    out_dir = config_path(config, "output_grounding_dir")
    rows = [item.model_dump(mode="json") for item in mappings]
    write_yaml(out_dir / "evidence_to_variable_map.yaml", {"mappings": rows})
    approved = sorted({name for item in mappings for name in item.approved_data_features})
    write_yaml(out_dir / "approved_variables_from_grounding.yaml", {"approved_variables": approved})
