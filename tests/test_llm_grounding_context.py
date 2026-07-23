from __future__ import annotations

import json
from pathlib import Path

import yaml

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.grounding.llm_context_compression import build_llm_grounding_context, write_llm_grounding_context
from sleep_ai_scientist.hypothesis.supervisor import HypothesisSupervisor
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord


def _evidence(
    evidence_id: str,
    mechanism: str,
    *,
    context: str,
    direction: EvidenceDirection = EvidenceDirection.support,
    score: float = 0.8,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        paper_id=f"paper_{evidence_id}",
        claim=f"{mechanism} claim {evidence_id}",
        mechanism=mechanism,
        direction=direction,
        modality="fMRI" if "network" in mechanism else "EEG",
        variable_or_feature="delta_power",
        evidence_context=context,
        downstream_role="direct_human_evidence" if context.startswith("human") else "background_mechanism",
        species="human" if context.startswith("human") else "mouse",
        final_evidence_score=score,
        evidence_quality_score=score,
        confidence_score=score,
    )


def test_llm_grounding_context_keeps_high_value_balanced_subset(tmp_path):
    evidence = [
        _evidence("e1", "slow-wave generation", context="animal_mechanistic", score=0.99),
        _evidence("e2", "slow-wave generation", context="human_clinical", score=0.7),
        _evidence("e3", "slow-wave generation", context="human_neuroimaging", score=0.6),
        _evidence("e4", "default mode network dysregulation", context="human_neuroimaging", score=0.9),
        _evidence("e5", "default mode network dysregulation", context="human_neuroimaging", direction=EvidenceDirection.unclear, score=0.95),
        _evidence("e6", "white matter integrity", context="human_neuroimaging", score=0.8),
        _evidence("e7", "white matter integrity", context="cellular_molecular", score=1.0),
    ]
    graph = {
        "nodes": [
            {"node_id": "finding:e2", "label": "finding e2", "node_type": "Finding", "metadata": {"evidence_id": "e2"}},
            {"node_id": "mechanism:slow-wave generation", "label": "slow-wave generation", "node_type": "Mechanism", "metadata": {}},
            {"node_id": "variable:delta_power", "label": "delta_power", "node_type": "Variable", "metadata": {}},
            {"node_id": "unused", "label": "unused", "node_type": "Paper", "metadata": {}},
        ],
        "edges": [
            {"source": "finding:e2", "target": "mechanism:slow-wave generation", "edge_type": "finding_supports_mechanism", "weight": 0.7, "metadata": {}},
            {"source": "mechanism:slow-wave generation", "target": "variable:delta_power", "edge_type": "mechanism_measured_by_variable", "weight": 1.0, "metadata": {}},
            {"source": "unused", "target": "mechanism:slow-wave generation", "edge_type": "paper_reports_finding", "weight": 1.0, "metadata": {}},
        ],
    }

    context = build_llm_grounding_context(
        evidence,
        graph,
        {
            "max_total_evidence": 4,
            "max_evidence_per_mechanism": 2,
            "max_graph_edges": 2,
            "max_unclear_fraction": 0.25,
        },
    )
    out = write_llm_grounding_context(context, tmp_path)

    selected = context["evidence_records"]
    assert len(selected) == 4
    assert {row["mechanism"] for row in selected} >= {"slow-wave generation", "default mode network dysregulation", "white matter integrity"}
    assert any(row["evidence_context"] == "human_clinical" for row in selected)
    assert sum(1 for row in selected if row["direction"] == "unclear") <= 1
    assert len(context["mechanism_graph"]["edges"]) <= 2
    assert "unused" not in {node["node_id"] for node in context["mechanism_graph"]["nodes"]}
    assert Path(out["llm_evidence_context_json"]).exists()
    assert Path(out["llm_mechanism_context_json"]).exists()
    manifest = json.loads(Path(out["llm_context_compression_manifest_json"]).read_text(encoding="utf-8"))
    assert manifest["source_evidence_count"] == 7
    assert manifest["selected_evidence_count"] == 4


def test_hypothesis_supervisor_prefers_compressed_llm_context_paths(tmp_path):
    original_evidence = [_evidence("original", "animal mechanism", context="animal_mechanistic")]
    compressed_evidence = [_evidence("compressed", "human mechanism", context="human_clinical")]
    original_graph = {"nodes": [{"node_id": "original", "label": "original", "node_type": "Mechanism", "metadata": {}}], "edges": []}
    compressed_graph = {"nodes": [{"node_id": "compressed", "label": "compressed", "node_type": "Mechanism", "metadata": {}}], "edges": []}
    paths = {
        "evidence_table_json": str(tmp_path / "evidence_table.json"),
        "knowledge_graph_json": str(tmp_path / "mechanism_graph.json"),
        "llm_evidence_context_json": str(tmp_path / "llm_evidence_context.json"),
        "llm_mechanism_context_json": str(tmp_path / "llm_mechanism_context.json"),
        "prior_hypotheses_json": str(tmp_path / "missing_priors.json"),
        "experimental_feedback": str(tmp_path / "missing_feedback.json"),
        "reward_memory": str(tmp_path / "missing_memory.json"),
        "output_hypotheses_dir": str(tmp_path / "hypotheses"),
        "report_path": str(tmp_path / "phase2_hypothesis_report.md"),
    }
    write_json(Path(paths["evidence_table_json"]), [item.model_dump(mode="json") for item in original_evidence])
    write_json(Path(paths["llm_evidence_context_json"]), [item.model_dump(mode="json") for item in compressed_evidence])
    write_json(Path(paths["knowledge_graph_json"]), original_graph)
    write_json(Path(paths["llm_mechanism_context_json"]), compressed_graph)
    config_path = tmp_path / "hypothesis.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": paths,
                "hypothesis": {"session_id": "test", "research_question": "test question"},
                "logging": {"progress": False},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    state = HypothesisSupervisor().create_state(config_path)

    assert [item.evidence_id for item in state.evidence_table] == ["compressed"]
    assert state.knowledge_graph["nodes"][0]["node_id"] == "compressed"
    assert str(state.artifacts["full_evidence_table_path"]).endswith("evidence_table.json")
    assert str(state.artifacts["evidence_table_path"]).endswith("llm_evidence_context.json")
