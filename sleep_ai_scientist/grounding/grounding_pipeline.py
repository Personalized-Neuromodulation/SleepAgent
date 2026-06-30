from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import config_path, existing_or_fixture, load_config
from sleep_ai_scientist.grounding.data_profile import (
    build_analysis_ready_profile,
    build_observed_profile,
    build_theoretical_profile,
    write_profiles,
)
from sleep_ai_scientist.grounding.evidence_extractor import extract_evidence, write_evidence_outputs
from sleep_ai_scientist.grounding.evidence_grader import grade_evidence_records
from sleep_ai_scientist.grounding.grounding_report import build_grounding_report, write_grounding_report
from sleep_ai_scientist.grounding.literature_loader import load_literature
from sleep_ai_scientist.grounding.mechanism_graph import build_mechanism_graph, write_graph_outputs
from sleep_ai_scientist.grounding.retrieval import retrieve
from sleep_ai_scientist.grounding.variable_mapper import map_variables, write_mapping_outputs


def run_grounding_pipeline(config_path_value: str | Path) -> dict[str, Any]:
    """Run Phase 1 end to end and write all grounding artifacts.

    Phase 1 is intentionally local and deterministic: it reads seed papers and
    Data Foundation tables, falls back to fixtures when real files are absent,
    and never modifies raw data or foundation inputs.
    """
    config = load_config(config_path_value)
    literature_path = existing_or_fixture(config, "seed_papers", "fixture_seed_papers")
    papers = load_literature(literature_path)

    retrieval_cfg = config.get("retrieval", {})
    if retrieval_cfg.get("enabled", False):
        hits = retrieve(str(retrieval_cfg.get("query", "")), papers, int(retrieval_cfg.get("top_k", 20)))
        selected_ids = {hit.paper_id for hit in hits}
        selected_papers = [paper for paper in papers if paper.paper_id in selected_ids]
    else:
        hits = []
        selected_papers = papers

    # Convert literature text into structured evidence before any data mapping.
    # The extractor is rule-based for Phase 1 so tests do not depend on LLM/API access.
    evidence = extract_evidence(selected_papers, default_population=config.get("evidence", {}).get("default_population", ""))
    evidence = grade_evidence_records(evidence)

    output_grounding_dir = config_path(config, "output_grounding_dir")
    write_evidence_outputs(evidence, output_grounding_dir)

    # Profiles keep theory and observed data separate. Only observed variables
    # passing approval/QC/missingness checks can enter analysis_ready_profile.
    theoretical = build_theoretical_profile(evidence)
    observed = build_observed_profile(config)
    analysis_ready = build_analysis_ready_profile(config, observed)
    write_profiles(config, theoretical, observed, analysis_ready)

    # Mapping is constrained to existing analysis-ready features. Missing
    # concepts are explicitly marked unavailable instead of invented.
    mappings = map_variables(evidence, analysis_ready, config_path(config, "variable_mapping_rules"))
    write_mapping_outputs(config, mappings)

    # The graph is a lightweight edge-list/JSON artifact for Phase 2 input, not
    # a persistent GraphRAG or Neo4j implementation.
    nodes, edges = build_mechanism_graph(
        selected_papers,
        evidence,
        mappings,
        mechanism_templates_path=config_path(config, "mechanism_templates"),
    )
    write_graph_outputs(nodes, edges, output_grounding_dir)

    report = build_grounding_report(selected_papers, evidence, nodes, edges, analysis_ready, mappings, config)
    report_path = config_path(config, "report_path")
    write_grounding_report(report_path, report)

    return {
        "papers": len(selected_papers),
        "retrieval_hits": len(hits),
        "evidence": len(evidence),
        "analysis_ready_variables": len(analysis_ready.features),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "report_path": str(report_path),
        "output_grounding_dir": str(output_grounding_dir),
        "output_profiles_dir": str(config_path(config, "output_profiles_dir")),
    }


def generate_grounding_report(config_path_value: str | Path) -> dict[str, Any]:
    return run_grounding_pipeline(config_path_value)
