from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import config_path, existing_or_fixture, load_config
from sleep_ai_scientist.api.literature_client import apply_query_config, search_literature_apis
from sleep_ai_scientist.common.io import read_yaml, write_json
from sleep_ai_scientist.grounding.evidence_audit import build_evidence_audit, write_evidence_audit
from sleep_ai_scientist.grounding.evidence_benchmark import run_evidence_benchmark
from sleep_ai_scientist.grounding.corpus_manifest import build_corpus_manifest, write_corpus_manifest
from sleep_ai_scientist.grounding.data_profile import (
    build_analysis_ready_profile,
    build_observed_profile,
    build_theoretical_profile,
    write_profiles,
)
from sleep_ai_scientist.grounding.evidence_extractor import extract_evidence, write_evidence_outputs
from sleep_ai_scientist.grounding.evidence_grader import evidence_quality_summary, grade_evidence_records
from sleep_ai_scientist.grounding.grounding_qc import run_grounding_qc, write_grounding_qc_report
from sleep_ai_scientist.grounding.grounding_report import build_grounding_report, write_grounding_report
from sleep_ai_scientist.grounding.literature_registry import merge_literature_registry, write_literature_registry
from sleep_ai_scientist.grounding.literature_loader import load_literature
from sleep_ai_scientist.grounding.mechanism_graph import build_mechanism_graph, write_graph_outputs
from sleep_ai_scientist.grounding.retrieval import retrieve
from sleep_ai_scientist.grounding.variable_mapper import map_variables, write_mapping_outputs
from sleep_ai_scientist.llm.evidence_verifier import EvidenceVerifier


def run_grounding_pipeline(
    config_path_value: str | Path,
    *,
    query_config_path: str | Path | None = None,
    corpus_version: str = "sleepagent_grounding_corpus_v1",
) -> dict[str, Any]:
    """Run knowledge grounding end to end and write all grounding artifacts.

    Knowledge grounding is intentionally local and deterministic: it reads seed papers and
    Data Foundation tables, falls back to fixtures when real files are absent,
    and never modifies raw data or foundation inputs.
    """
    config = apply_query_config(load_config(config_path_value), query_config_path)
    config["corpus_version"] = corpus_version
    evidence_rules_path = config_path(config, "evidence_extraction_rules", "configs/evidence_extraction_rules.yaml")
    llm_config_path = config_path(config, "llm_config", "configs/llm_config.yaml")
    llm_config = read_yaml(llm_config_path) if llm_config_path.exists() else {}
    literature_path = existing_or_fixture(config, "seed_papers", "fixture_seed_papers")
    seed_papers = load_literature(literature_path)
    api_papers, api_summary = search_literature_apis(config)
    papers, duplicate_reports = merge_literature_registry(seed_papers, api_papers)
    api_summary["seed_count"] = len(seed_papers)
    api_summary["final_literature_count"] = len(papers)
    write_literature_registry(
        papers,
        config_path(config, "literature_registry_csv", "data/literature/literature_registry.csv"),
        config_path(config, "literature_registry_jsonl", "data/literature/literature_registry.jsonl"),
        config_path(config, "literature_deduplication_report", "outputs/grounding/literature_deduplication_report.csv"),
        duplicate_reports,
    )

    retrieval_cfg = config.get("retrieval", {})
    if retrieval_cfg.get("enabled", False):
        hits = retrieve(str(retrieval_cfg.get("query", "")), papers, int(retrieval_cfg.get("top_k", 20)))
        selected_ids = {hit.paper_id for hit in hits}
        selected_papers = [paper for paper in papers if paper.paper_id in selected_ids]
    else:
        hits = []
        selected_papers = papers

    # Convert literature text into structured evidence before any data mapping.
    # The extractor is rule-based so tests do not depend on LLM/API access.
    output_grounding_dir = config_path(config, "output_grounding_dir")
    llm_enabled = bool(llm_config.get("llm", {}).get("enabled", False) and llm_config.get("evidence_extraction", {}).get("llm_assist_enabled", False))
    verifier = EvidenceVerifier(
        client=None,
        log_file=llm_config.get("llm", {}).get("log_file", output_grounding_dir / "llm_extraction_log.jsonl"),
        excluded_log_file=output_grounding_dir / "excluded_evidence_log.jsonl",
        fail_open=bool(llm_config.get("llm", {}).get("fail_open", True)),
    ) if llm_enabled else None
    evidence = extract_evidence(
        selected_papers,
        default_population=config.get("evidence", {}).get("default_population", ""),
        rules_path=evidence_rules_path,
        llm_verifier=verifier,
        llm_config=llm_config,
    )
    evidence = grade_evidence_records(evidence)
    write_evidence_outputs(evidence, output_grounding_dir)
    quality_summary = evidence_quality_summary(evidence)
    write_json(output_grounding_dir / "evidence_quality_summary.json", quality_summary)
    llm_stats = {
        "enabled": llm_enabled,
        "provider": llm_config.get("llm", {}).get("provider", ""),
        "model": llm_config.get("llm", {}).get("model", ""),
        "calls_attempted": getattr(verifier, "calls_attempted", 0),
        "calls_succeeded": getattr(verifier, "calls_succeeded", 0),
        "calls_failed": getattr(verifier, "calls_failed", 0),
        "revised_evidence_count": getattr(verifier, "revised_evidence_count", 0),
        "split_claim_count": getattr(verifier, "split_claim_count", 0),
        "excluded_claim_count": getattr(verifier, "excluded_claim_count", 0),
        "failure_fallback_used": bool(getattr(verifier, "calls_failed", 0)),
        "log_file": llm_config.get("llm", {}).get("log_file", str(output_grounding_dir / "llm_extraction_log.jsonl")),
        "excluded_evidence_log": str(output_grounding_dir / "excluded_evidence_log.jsonl"),
    }
    audit = build_evidence_audit(
        selected_papers,
        evidence,
        [str(item) for item in config.get("evidence", {}).get("preferred_mechanisms", [])],
        llm_stats,
    )
    write_evidence_audit(output_grounding_dir, audit, selected_papers, evidence)
    gold_path = config_path(config, "evidence_goldset", "data/fixtures/evidence_goldset/gold_evidence.csv")
    benchmark = run_evidence_benchmark(evidence, gold_path, output_grounding_dir / "evidence_extraction_benchmark.json") if gold_path.exists() else {}

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

    # The graph is a lightweight edge-list/JSON artifact for scientific-loop input, not
    # a persistent GraphRAG or Neo4j implementation.
    nodes, edges = build_mechanism_graph(
        selected_papers,
        evidence,
        mappings,
        mechanism_templates_path=config_path(config, "mechanism_templates"),
    )
    write_graph_outputs(nodes, edges, output_grounding_dir)

    qc_report = run_grounding_qc(
        selected_papers,
        evidence,
        mappings,
        analysis_ready,
        [str(item) for item in config.get("evidence", {}).get("preferred_mechanisms", [])],
    )
    write_grounding_qc_report(output_grounding_dir / "grounding_qc_report.json", qc_report)

    manifest = build_corpus_manifest(config, corpus_version, api_summary)
    manifest_path = config_path(config, "corpus_manifest", "outputs/grounding/corpus_manifest.json")
    write_corpus_manifest(manifest_path, manifest)

    report = build_grounding_report(
        selected_papers,
        evidence,
        nodes,
        edges,
        analysis_ready,
        mappings,
        config,
        api_summary,
        manifest=manifest,
        quality_summary=quality_summary,
        qc_report=qc_report,
        evidence_audit=audit,
        evidence_benchmark=benchmark,
        llm_stats=llm_stats,
    )
    report_path = config_path(config, "report_path")
    write_grounding_report(report_path, report)
    phase1_report_path = config_path(config, "phase1_report_path", "reports/phase1_grounding_report.md")
    if phase1_report_path != report_path:
        write_grounding_report(phase1_report_path, report)

    return {
        "papers": len(selected_papers),
        "seed_papers": len(seed_papers),
        "api_papers": len(api_papers),
        "retrieval_hits": len(hits),
        "evidence": len(evidence),
        "analysis_ready_variables": len(analysis_ready.features),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "corpus_version": corpus_version,
        "corpus_manifest": str(manifest_path),
        "literature_registry": str(config_path(config, "literature_registry_csv", "data/literature/literature_registry.csv")),
        "evidence_quality_summary": quality_summary,
        "grounding_qc_report": str(output_grounding_dir / "grounding_qc_report.json"),
        "evidence_audit": str(output_grounding_dir / "evidence_extraction_audit.json"),
        "evidence_benchmark": str(output_grounding_dir / "evidence_extraction_benchmark.json") if benchmark else "",
        "report_path": str(report_path),
        "output_grounding_dir": str(output_grounding_dir),
        "output_profiles_dir": str(config_path(config, "output_profiles_dir")),
        "api_summary": api_summary,
    }


def generate_grounding_report(config_path_value: str | Path) -> dict[str, Any]:
    return run_grounding_pipeline(config_path_value)
