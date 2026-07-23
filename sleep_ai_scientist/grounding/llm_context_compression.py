from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.schemas.evidence import EvidenceRecord

PREFERRED_CONTEXTS = {
    "human_clinical": 5.0,
    "human_neuroimaging": 4.8,
    "human_general_sleep": 3.5,
    "translational_mechanistic_support": 2.5,
    "animal_mechanistic": 2.0,
    "cellular_molecular": 1.0,
}

PREFERRED_DIRECTIONS = {
    "support": 3.0,
    "refute": 3.0,
    "null": 2.5,
    "unclear": 0.5,
}

PREFERRED_MECHANISMS = {
    "insomnia severity": 3.0,
    "slow-wave generation": 2.8,
    "spindle generation": 2.7,
    "thalamocortical coupling": 2.7,
    "default mode network dysregulation": 2.6,
    "white matter integrity": 2.5,
    "hyperarousal": 2.4,
    "confound / methodological limitation": 2.3,
    "limbic structural vulnerability": 2.0,
    "salience network dysregulation": 2.0,
}


def build_llm_grounding_context(evidence: list[EvidenceRecord], graph: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or {}
    max_total = int(cfg.get("max_total_evidence", 80))
    max_per_mechanism = int(cfg.get("max_evidence_per_mechanism", 8))
    max_unclear_fraction = float(cfg.get("max_unclear_fraction", 0.25))
    max_graph_edges = int(cfg.get("max_graph_edges", 180))
    selected = _select_evidence(evidence, max_total=max_total, max_per_mechanism=max_per_mechanism, max_unclear_fraction=max_unclear_fraction)
    compact_graph = _compress_graph(graph, selected, max_edges=max_graph_edges)
    return {
        "evidence_records": [item.model_dump(mode="json") for item in selected],
        "mechanism_graph": compact_graph,
        "manifest": _manifest(evidence, selected, graph, compact_graph, cfg),
    }


def write_llm_grounding_context(context: dict[str, Any], output_dir: Path) -> dict[str, str]:
    paths = {
        "llm_evidence_context_json": output_dir / "llm_evidence_context.json",
        "llm_mechanism_context_json": output_dir / "llm_mechanism_context.json",
        "llm_context_compression_manifest_json": output_dir / "llm_context_compression_manifest.json",
    }
    write_json(paths["llm_evidence_context_json"], context["evidence_records"])
    write_json(paths["llm_mechanism_context_json"], context["mechanism_graph"])
    write_json(paths["llm_context_compression_manifest_json"], context["manifest"])
    return {key: str(value) for key, value in paths.items()}


def _select_evidence(evidence: list[EvidenceRecord], *, max_total: int, max_per_mechanism: int, max_unclear_fraction: float) -> list[EvidenceRecord]:
    by_mechanism: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for item in evidence:
        by_mechanism[item.mechanism or "unknown"].append(item)
    for values in by_mechanism.values():
        values.sort(key=_evidence_score, reverse=True)

    selected: list[EvidenceRecord] = []
    mechanism_order = sorted(by_mechanism, key=lambda mechanism: _mechanism_priority(mechanism, by_mechanism[mechanism]), reverse=True)
    while len(selected) < max_total:
        changed = False
        for mechanism in mechanism_order:
            if len(selected) >= max_total:
                break
            current_count = sum(1 for item in selected if (item.mechanism or "unknown") == mechanism)
            if current_count >= max_per_mechanism:
                continue
            candidate = _next_allowed_candidate(by_mechanism[mechanism], selected, max_total=max_total, max_unclear_fraction=max_unclear_fraction)
            if candidate is None:
                continue
            selected.append(candidate)
            changed = True
        if not changed:
            break
    selected.sort(key=_evidence_score, reverse=True)
    return selected[:max_total]


def _next_allowed_candidate(candidates: list[EvidenceRecord], selected: list[EvidenceRecord], *, max_total: int, max_unclear_fraction: float) -> EvidenceRecord | None:
    selected_ids = {item.evidence_id for item in selected}
    unclear_limit = max(1, int(max_total * max_unclear_fraction))
    unclear_count = sum(1 for item in selected if _direction(item) == "unclear")
    for item in candidates:
        if item.evidence_id in selected_ids:
            continue
        if _direction(item) == "unclear" and unclear_count >= unclear_limit:
            continue
        return item
    return None


def _evidence_score(item: EvidenceRecord) -> float:
    quality = item.final_evidence_score or item.evidence_quality_score or item.confidence_score or 0.0
    return (
        float(quality) * 4.0
        + PREFERRED_CONTEXTS.get(str(item.evidence_context or ""), 0.8)
        + PREFERRED_DIRECTIONS.get(_direction(item), 0.0)
        + PREFERRED_MECHANISMS.get(str(item.mechanism or ""), 0.0)
        + (0.4 if item.variable_or_feature else 0.0)
        + (0.3 if item.modality else 0.0)
    )


def _mechanism_priority(mechanism: str, values: list[EvidenceRecord]) -> float:
    best = max((_evidence_score(item) for item in values), default=0.0)
    return PREFERRED_MECHANISMS.get(mechanism, 0.0) + best


def _direction(item: EvidenceRecord) -> str:
    value = item.direction.value if hasattr(item.direction, "value") else item.direction
    return str(value)


def _compress_graph(graph: dict[str, Any], selected: list[EvidenceRecord], *, max_edges: int) -> dict[str, Any]:
    if not isinstance(graph, dict):
        return {"nodes": [], "edges": []}
    evidence_ids = {item.evidence_id for item in selected}
    mechanisms = {item.mechanism for item in selected if item.mechanism}
    variables = {item.variable_or_feature for item in selected if item.variable_or_feature}
    modalities = {item.modality for item in selected if item.modality}
    node_by_id = {str(node.get("node_id")): node for node in graph.get("nodes", []) if isinstance(node, dict)}
    relevant_nodes = {
        node_id
        for node_id, node in node_by_id.items()
        if _node_relevant(node, evidence_ids, mechanisms, variables, modalities)
    }
    scored_edges = []
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or edge.get("source_id") or "")
        target = str(edge.get("target") or edge.get("target_id") or "")
        score = _edge_score(edge, source, target, relevant_nodes)
        if score <= 0:
            continue
        scored_edges.append((score, edge, source, target))
    scored_edges.sort(key=lambda item: item[0], reverse=True)
    kept_edges = []
    kept_node_ids = set(relevant_nodes)
    for _, edge, source, target in scored_edges[:max_edges]:
        kept_edges.append(edge)
        kept_node_ids.update([source, target])
    kept_nodes = [node for node_id, node in node_by_id.items() if node_id in kept_node_ids]
    return {"nodes": kept_nodes, "edges": kept_edges}


def _node_relevant(node: dict[str, Any], evidence_ids: set[str], mechanisms: set[str], variables: set[str], modalities: set[str]) -> bool:
    label = str(node.get("label") or "")
    node_id = str(node.get("node_id") or "")
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    return (
        str(metadata.get("evidence_id") or "") in evidence_ids
        or node_id.removeprefix("finding:") in evidence_ids
        or label in mechanisms
        or label in variables
        or label in modalities
    )


def _edge_score(edge: dict[str, Any], source: str, target: str, relevant_nodes: set[str]) -> float:
    edge_type = str(edge.get("edge_type") or "")
    score = 0.0
    if source in relevant_nodes:
        score += 2.0
    if target in relevant_nodes:
        score += 2.0
    if edge_type in {"finding_supports_mechanism", "finding_refutes_mechanism", "finding_null_for_mechanism"}:
        score += 3.0
    elif edge_type in {"mechanism_measured_by_variable", "variable_belongs_to_modality", "variable_mapped_to_data_feature"}:
        score += 2.0
    return score


def _manifest(evidence: list[EvidenceRecord], selected: list[EvidenceRecord], graph: dict[str, Any], compact_graph: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    selected_contexts = Counter(str(item.evidence_context or "unknown") for item in selected)
    selected_directions = Counter(_direction(item) for item in selected)
    selected_mechanisms = Counter(str(item.mechanism or "unknown") for item in selected)
    return {
        "compression": "llm_grounding_context_v1",
        "source_evidence_count": len(evidence),
        "selected_evidence_count": len(selected),
        "source_graph_nodes": len(graph.get("nodes", [])) if isinstance(graph, dict) else 0,
        "source_graph_edges": len(graph.get("edges", [])) if isinstance(graph, dict) else 0,
        "selected_graph_nodes": len(compact_graph.get("nodes", [])),
        "selected_graph_edges": len(compact_graph.get("edges", [])),
        "selected_evidence_contexts": dict(selected_contexts),
        "selected_directions": dict(selected_directions),
        "selected_mechanisms": dict(selected_mechanisms),
        "config": config,
    }
