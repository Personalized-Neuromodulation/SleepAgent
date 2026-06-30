from __future__ import annotations

from collections import Counter
from pathlib import Path

from sleep_ai_scientist.common.config import config_path
from sleep_ai_scientist.common.io import write_yaml
from sleep_ai_scientist.schemas.data_profile import DataProfile, VariableMappingRecord
from sleep_ai_scientist.schemas.evidence import EvidenceRecord
from sleep_ai_scientist.schemas.graph import GraphEdge, GraphNode
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def build_grounding_report(
    papers: list[LiteratureRecord],
    evidence: list[EvidenceRecord],
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    analysis_ready: DataProfile,
    mappings: list[VariableMappingRecord],
    config: dict,
) -> str:
    direction_counts = Counter(item.direction.value for item in evidence)
    quality_scores = [item.evidence_quality_score or 0.0 for item in evidence]
    unavailable = [item for item in mappings if item.mapping_status.value == "unavailable"]
    ambiguous = [item for item in mappings if item.mapping_status.value == "ambiguous"]
    confounds = sorted({node.label for node in nodes if node.node_type.value == "Confound"})
    output_grounding = config_path(config, "output_grounding_dir")
    output_profiles = config_path(config, "output_profiles_dir")
    lines = [
        "# Phase 1 Grounding Report",
        "",
        "## Summary",
        "",
        f"- Literature records: {len(papers)}",
        f"- Evidence records: {len(evidence)}",
        f"- Mechanism graph nodes: {len(nodes)}",
        f"- Mechanism graph edges: {len(edges)}",
        "",
        "## Evidence Direction Counts",
        "",
    ]
    for key in ["support", "refute", "null", "unclear"]:
        lines.append(f"- {key}: {direction_counts.get(key, 0)}")
    lines.extend(["", "## Evidence Quality", ""])
    if quality_scores:
        lines.append(f"- min: {min(quality_scores):.3f}")
        lines.append(f"- mean: {sum(quality_scores) / len(quality_scores):.3f}")
        lines.append(f"- max: {max(quality_scores):.3f}")
    else:
        lines.append("- no evidence")
    lines.extend(["", "## Analysis-Ready Variables", ""])
    for item in analysis_ready.features:
        lines.append(f"- `{item.feature_name}` ({item.modality}, role={item.role}, missing={item.missing_rate})")
    lines.extend(["", "## Unavailable But Theoretically Relevant Variables", ""])
    for item in unavailable:
        lines.append(f"- `{item.concept}` candidates={item.candidate_variables}")
    lines.extend(["", "## Ambiguous Mappings", ""])
    for item in ambiguous:
        lines.append(f"- `{item.concept}` approved={item.approved_data_features}")
    lines.extend(["", "## Main Confounds", ""])
    for item in confounds:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Phase 2 Input Files",
            "",
            f"- `{output_grounding / 'evidence_table.csv'}`",
            f"- `{output_grounding / 'evidence_table.json'}`",
            f"- `{output_grounding / 'mechanism_graph_nodes.csv'}`",
            f"- `{output_grounding / 'mechanism_graph_edges.csv'}`",
            f"- `{output_grounding / 'mechanism_graph.json'}`",
            f"- `{output_grounding / 'evidence_to_variable_map.yaml'}`",
            f"- `{output_grounding / 'approved_variables_from_grounding.yaml'}`",
            f"- `{output_profiles / 'theoretical_profile.yaml'}`",
            f"- `{output_profiles / 'observed_profile.yaml'}`",
            f"- `{output_profiles / 'analysis_ready_profile.yaml'}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_grounding_report(path: Path, report: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
