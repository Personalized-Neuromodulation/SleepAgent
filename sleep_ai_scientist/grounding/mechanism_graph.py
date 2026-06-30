from __future__ import annotations

from pathlib import Path

from sleep_ai_scientist.common.io import read_yaml, write_csv, write_json
from sleep_ai_scientist.schemas.data_profile import VariableMappingRecord
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord
from sleep_ai_scientist.schemas.graph import EdgeType, GraphEdge, GraphNode, NodeType
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def _add_node(nodes: dict[str, GraphNode], node_id: str, label: str, node_type: NodeType, **metadata) -> None:
    """Add a graph node once while preserving first metadata assignment."""
    nodes.setdefault(node_id, GraphNode(node_id=node_id, label=label, node_type=node_type, metadata=metadata))


def build_mechanism_graph(
    papers: list[LiteratureRecord],
    evidence: list[EvidenceRecord],
    mappings: list[VariableMappingRecord],
    mechanism_templates_path: Path | None = None,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Build a lightweight mechanism graph from papers, evidence, and mappings."""
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    paper_by_id = {paper.paper_id: paper for paper in papers}

    for item in evidence:
        paper = paper_by_id.get(item.paper_id)
        # Evidence creates the core chain:
        # Paper -> Finding -> Mechanism -> Variable -> Modality.
        paper_node = f"paper:{item.paper_id}"
        finding_node = f"finding:{item.evidence_id}"
        mechanism_node = f"mechanism:{item.mechanism}"
        variable_node = f"variable:{item.variable_or_feature}"
        modality_node = f"modality:{item.modality}"
        _add_node(nodes, paper_node, paper.title if paper else item.paper_id, NodeType.Paper, paper_id=item.paper_id)
        _add_node(nodes, finding_node, item.claim, NodeType.Finding, evidence_id=item.evidence_id)
        _add_node(nodes, mechanism_node, item.mechanism, NodeType.Mechanism)
        _add_node(nodes, variable_node, item.variable_or_feature, NodeType.Variable)
        _add_node(nodes, modality_node, item.modality, NodeType.Modality)
        edges.append(GraphEdge(source=paper_node, target=finding_node, edge_type=EdgeType.paper_reports_finding))
        edge_type = EdgeType.finding_refutes_mechanism if item.direction == EvidenceDirection.refute else EdgeType.finding_supports_mechanism
        edges.append(GraphEdge(source=finding_node, target=mechanism_node, edge_type=edge_type, weight=item.evidence_quality_score or 1.0))
        edges.append(GraphEdge(source=mechanism_node, target=variable_node, edge_type=EdgeType.mechanism_measured_by_variable))
        edges.append(GraphEdge(source=variable_node, target=modality_node, edge_type=EdgeType.variable_belongs_to_modality))

    for mapping in mappings:
        # Approved mappings add the concrete DataFeature layer. Unavailable
        # mappings are still kept in YAML output but do not create fake features.
        for feature in mapping.approved_data_features:
            feature_node = f"data_feature:{feature}"
            variable_node = f"variable:{feature}"
            _add_node(nodes, feature_node, feature, NodeType.DataFeature)
            _add_node(nodes, variable_node, feature, NodeType.Variable)
            edges.append(GraphEdge(source=variable_node, target=feature_node, edge_type=EdgeType.variable_mapped_to_data_feature, weight=mapping.mapping_confidence))

    if mechanism_templates_path and mechanism_templates_path.exists():
        # Confounds are configured globally and connected weakly to variables so
        # Phase 2 can see what should be controlled or reviewed.
        payload = read_yaml(mechanism_templates_path)
        for confound in payload.get("confounds", []):
            confound_node = f"confound:{confound}"
            _add_node(nodes, confound_node, str(confound), NodeType.Confound)
            for node in list(nodes.values()):
                if node.node_type == NodeType.Variable:
                    edges.append(GraphEdge(source=confound_node, target=node.node_id, edge_type=EdgeType.confound_affects_variable, weight=0.2))

    return list(nodes.values()), edges


def write_graph_outputs(nodes: list[GraphNode], edges: list[GraphEdge], out_dir: Path) -> None:
    """Persist graph in CSV edge-list form and a JSON bundle."""
    node_rows = [node.model_dump(mode="json") for node in nodes]
    edge_rows = [edge.model_dump(mode="json") for edge in edges]
    write_csv(out_dir / "mechanism_graph_nodes.csv", node_rows)
    write_csv(out_dir / "mechanism_graph_edges.csv", edge_rows)
    write_json(out_dir / "mechanism_graph.json", {"nodes": node_rows, "edges": edge_rows})
