from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sleep_ai_scientist.common.config import config_path
from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.hypothesis.agents.state import HypothesisSessionState
from sleep_ai_scientist.hypothesis.agents.memory import build_prior_block, build_rlef_injection_block, retrieve_relevant_priors
from sleep_ai_scientist.schemas.evidence import EvidenceRecord


class ContextAgent:
    name = "ContextAgent"

    def run(self, state: HypothesisSessionState) -> HypothesisSessionState:
        config = state.config
        rlef_cfg = config.get("rlef", {})
        priors = retrieve_relevant_priors(
            state.reward_memory,
            state.research_question,
            top_k=int(rlef_cfg.get("prior_top_k", 5)),
            embedding_config=config.get("embedding", {}),
        )
        state.context_blocks = {
            "research_question": state.research_question,
            "evidence": _format_evidence_summary(state.evidence_table),
            "knowledge_graph": _format_knowledge_graph(state.knowledge_graph),
            "prior_hypotheses": _format_prior_hypotheses(state.prior_hypotheses),
            "prior_context": build_prior_block(priors),
            "rlef_context": build_rlef_injection_block(state.experimental_feedback),
        }
        state.artifacts["retrieved_priors"] = priors
        context_path = config_path(config, "context_blocks_json", "outputs/hypotheses/context_blocks.json")
        write_json(
            context_path,
            {
                "research_question": state.context_blocks["research_question"],
                "evidence": state.context_blocks["evidence"],
                "knowledge_graph": state.context_blocks["knowledge_graph"],
                "prior_hypotheses": state.context_blocks["prior_hypotheses"],
                "prior_context": state.context_blocks["prior_context"],
                "rlef_context": state.context_blocks["rlef_context"],
                "retrieved_priors": [item.model_dump(mode="json") for item in priors],
            },
        )
        state.artifacts["context_blocks_path"] = context_path
        return state


def _format_evidence_summary(evidence: list[EvidenceRecord], limit: int = 12) -> str:
    if not evidence:
        return "No evidence records were provided."
    mechanisms = Counter(item.mechanism for item in evidence if item.mechanism)
    modalities = Counter(item.modality for item in evidence if item.modality)
    lines = [
        f"Evidence records: {len(evidence)}",
        "Top mechanisms: " + ", ".join(term for term, _ in mechanisms.most_common(8)),
        "Top modalities: " + ", ".join(term for term, _ in modalities.most_common(8)),
        "",
        "Representative evidence:",
    ]
    for index, item in enumerate(evidence[:limit], start=1):
        direction = item.direction.value if hasattr(item.direction, "value") else item.direction
        quality = item.evidence_quality_score if item.evidence_quality_score is not None else item.confidence_score
        lines.append(
            f"[E{index}] {item.evidence_id} | paper={item.paper_id} | mechanism={item.mechanism} | "
            f"variable={item.variable_or_feature} | modality={item.modality} | direction={direction} | quality={quality}: {item.claim}"
        )
    return "\n".join(lines)


def _format_knowledge_graph(graph: dict[str, Any], limit: int = 24) -> str:
    if not graph:
        return "No knowledge graph was provided."
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    labels = {str(node.get("node_id", "")): str(node.get("label", "")) for node in nodes if isinstance(node, dict)}
    node_counts = Counter(str(node.get("node_type", "")) for node in nodes if isinstance(node, dict))
    edge_counts = Counter(str(edge.get("edge_type", "")) for edge in edges if isinstance(edge, dict))
    mechanism_variables: dict[str, set[str]] = defaultdict(set)
    support_edges: list[str] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source_id") or edge.get("source") or "")
        target = str(edge.get("target_id") or edge.get("target") or "")
        edge_type = str(edge.get("edge_type", ""))
        if edge_type == "mechanism_measured_by_variable":
            mechanism_variables[labels.get(source, source)].add(labels.get(target, target))
        elif "supports" in edge_type or "refutes" in edge_type:
            support_edges.append(f"{labels.get(source, source)} --{edge_type}--> {labels.get(target, target)}")

    lines = [
        f"Knowledge graph nodes: {len(nodes)}; edges: {len(edges)}",
        "Node types: " + ", ".join(f"{key}={value}" for key, value in node_counts.most_common()),
        "Edge types: " + ", ".join(f"{key}={value}" for key, value in edge_counts.most_common()),
        "",
        "Mechanism-variable paths:",
    ]
    for mechanism, variables in list(mechanism_variables.items())[:limit]:
        lines.append(f"- {mechanism}: {', '.join(sorted(variables))}")
    if support_edges:
        lines.extend(["", "Evidence-mechanism relations:"])
        lines.extend(f"- {item}" for item in support_edges[:limit])
    return "\n".join(lines)


def _format_prior_hypotheses(priors: list[Any], limit: int = 8) -> str:
    if not priors:
        return "No prior hypotheses were provided."
    return "\n".join(f"- {item.title}: {item.summary}" for item in priors[:limit])
