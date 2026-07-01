from __future__ import annotations

from collections import Counter
from pathlib import Path

from sleep_ai_scientist.common.config import config_path
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
    api_summary: dict | None = None,
    manifest: dict | None = None,
    quality_summary: dict | None = None,
    qc_report: dict | None = None,
    evidence_audit: dict | None = None,
    evidence_benchmark: dict | None = None,
    llm_stats: dict | None = None,
) -> str:
    direction_counts = Counter(item.direction.value for item in evidence)
    quality_scores = [item.evidence_quality_score or 0.0 for item in evidence]
    unavailable = [item for item in mappings if item.mapping_status.value == "unavailable"]
    ambiguous = [item for item in mappings if item.mapping_status.value == "ambiguous"]
    mapped = [item for item in mappings if item.mapping_status.value == "mapped"]
    confounds = sorted({node.label for node in nodes if node.node_type.value == "Confound"})
    output_grounding = config_path(config, "output_grounding_dir")
    output_profiles = config_path(config, "output_profiles_dir")
    audit = evidence_audit or {}
    benchmark = evidence_benchmark or {}
    llm = llm_stats or {}
    lines = [
        "# Knowledge Grounding Report",
        "",
        "## Summary",
        "",
        f"- Literature records: {len(papers)}",
        f"- Evidence records: {len(evidence)}",
        f"- Mechanism graph nodes: {len(nodes)}",
        f"- Mechanism graph edges: {len(edges)}",
        "",
        "## Grounding Corpus Build",
        "",
        f"- Corpus version: {(manifest or {}).get('corpus_version', config.get('corpus_version', ''))}",
        f"- Query set version: {(manifest or {}).get('query_set_version', '')}",
        f"- Build time: {(manifest or {}).get('created_at', '')}",
        f"- API enabled: {bool((api_summary or {}).get('enabled', False))}",
        f"- Providers: {', '.join((manifest or {}).get('providers', [])) or 'none'}",
        f"- Query count: {(api_summary or {}).get('query_count', 0)}",
        f"- Seed literature count: {(api_summary or {}).get('seed_count', 0)}",
        f"- API raw retrieved count: {(api_summary or {}).get('raw_count', 0)}",
        f"- API deduplicated count: {(api_summary or {}).get('deduplicated_count', 0)}",
        f"- Final literature count: {(api_summary or {}).get('final_literature_count', len(papers))}",
        f"- Evidence count: {len(evidence)}",
        f"- High-quality evidence count: {(quality_summary or {}).get('high_quality_evidence_count', 0)}",
        f"- Mechanism graph nodes: {len(nodes)}",
        f"- Mechanism graph edges: {len(edges)}",
        f"- Mapped concepts: {len(mapped)}",
        f"- Ambiguous concepts: {len(ambiguous)}",
        f"- Unavailable concepts: {len(unavailable)}",
        f"- Fallback used: {not bool((api_summary or {}).get('enabled', False)) or bool((api_summary or {}).get('warnings', []))}",
        f"- Output manifest: {config_path(config, 'corpus_manifest', 'outputs/grounding/corpus_manifest.json')}",
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
            "## API Literature Retrieval",
            "",
            f"- API enabled: {bool((api_summary or {}).get('enabled', False))}",
            f"- Providers used: {', '.join(sorted((api_summary or {}).get('provider_counts', {}).keys())) or 'none'}",
            f"- Search query count: {(api_summary or {}).get('query_count', 0)}",
            f"- Records retrieved per provider: {(api_summary or {}).get('provider_counts', {})}",
            "- Provider-level results:",
            f"  - PubMed: {((api_summary or {}).get('provider_counts', {})).get('pubmed', 0)}",
            f"  - Europe PMC: {((api_summary or {}).get('provider_counts', {})).get('europe_pmc', 0)}",
            f"  - OpenAlex: {((api_summary or {}).get('provider_counts', {})).get('openalex', 0)}",
            f"  - Semantic Scholar: {((api_summary or {}).get('provider_counts', {})).get('semantic_scholar', 0)}",
            f"- API records before deduplication: {(api_summary or {}).get('raw_count', 0)}",
            f"- API records after deduplication: {(api_summary or {}).get('deduplicated_count', 0)}",
            f"- Seed literature count: {(api_summary or {}).get('seed_count', len(papers))}",
            f"- Final literature count: {(api_summary or {}).get('final_literature_count', len(papers))}",
            f"- API errors: {'; '.join((api_summary or {}).get('errors', [])) or 'none'}",
            f"- API warnings: {'; '.join((api_summary or {}).get('warnings', [])) or 'none'}",
            f"- Cache enabled: {(api_summary or {}).get('cache_enabled', False)}",
            f"- Cache hit count if available: {(api_summary or {}).get('cache_hit_count', 'unavailable')}",
            f"- Cache directory: {(api_summary or {}).get('cache_dir', '')}",
            "",
            "## Data Grounding",
            "",
            f"- Analysis-ready features: {len(analysis_ready.features)}",
            f"- Mapped variables: {sorted({name for item in mappings for name in item.approved_data_features})}",
            f"- Unavailable theory-only concepts: {[item.concept for item in unavailable]}",
            "- Major confounds:",
            "  - mean_FD",
            "  - in_scanner_sleep_time",
            "  - medication",
            "  - age",
            "  - sex",
            "",
            "## Grounding QC",
            "",
            f"- Passed: {(qc_report or {}).get('passed', False)}",
            f"- Warnings: {'; '.join((qc_report or {}).get('warnings', [])) or 'none'}",
            f"- Errors: {'; '.join((qc_report or {}).get('errors', [])) or 'none'}",
            f"- Recommended next steps: {'; '.join((qc_report or {}).get('recommended_next_steps', [])) or 'none'}",
            "",
            "## Evidence Extraction Completeness",
            "",
            f"- Total papers: {audit.get('total_papers', len(papers))}",
            f"- Papers with evidence: {audit.get('papers_with_evidence', 0)}",
            f"- Papers without evidence: {audit.get('papers_without_evidence', 0)}",
            f"- Evidence count: {audit.get('evidence_count', len(evidence))}",
            f"- Evidence per paper: mean={audit.get('evidence_per_paper_mean', 0)}, median={audit.get('evidence_per_paper_median', 0)}",
            f"- Direction counts: {audit.get('direction_counts', {})}",
            f"- Mechanism coverage: {audit.get('mechanism_counts', {})}",
            f"- Mechanisms with zero evidence: {audit.get('mechanisms_with_zero_evidence', [])}",
            f"- Missing variable rate: {audit.get('missing_variable_rate', 0)}",
            f"- Missing modality rate: {audit.get('missing_modality_rate', 0)}",
            f"- Unclear direction rate: {audit.get('unclear_direction_rate', 0)}",
            f"- Possible positive evidence bias: {audit.get('possible_positive_evidence_bias', False)}",
            f"- Unmatched relevant papers: {audit.get('top_unmatched_relevant_papers', [])[:10]}",
            "",
            "## Evidence Quality and Feasibility",
            "",
            f"- Mean extraction confidence score: {audit.get('mean_extraction_confidence_score', 0)}",
            f"- Mean evidence quality score: {audit.get('mean_evidence_quality_score', 0)}",
            f"- Mean mechanistic strength score: {audit.get('mean_mechanistic_strength_score', 0)}",
            f"- Mean clinical applicability score: {audit.get('mean_clinical_applicability_score', 0)}",
            f"- Mean evidence feasibility score: {audit.get('mean_evidence_feasibility_score', 0)}",
            f"- Mean final evidence score: {audit.get('mean_final_evidence_score', 0)}",
            f"- High feasibility evidence count: {(quality_summary or {}).get('high_feasibility_evidence_count', 0)}",
            f"- High citation but low feasibility evidence: {sum(1 for item in evidence if (item.citation_count_age_normalized or 0) > 25 and (item.evidence_feasibility_score or 0) < 0.4)}",
            f"- High mechanistic but low clinical applicability evidence: {sum(1 for item in evidence if (item.mechanistic_strength_score or 0) >= 0.75 and (item.clinical_applicability_score or 0) <= 0.4)}",
            "",
            "## Citation and Journal Metadata",
            "",
            f"- Citation availability rate: {audit.get('citation_availability_rate', 0)}",
            f"- Journal availability rate: {audit.get('journal_availability_rate', 0)}",
            f"- Median citation count: {audit.get('median_citation_count', 0)}",
            f"- Citation source breakdown: {dict(Counter(item.citation_source or 'missing' for item in evidence))}",
            f"- Journal metric availability: {round(sum(1 for item in evidence if item.journal_impact_factor is not None or item.journal_quartile) / len(evidence), 3) if evidence else 0}",
            "- Note: citation and journal metrics are auxiliary and not primary evidence quality determinants.",
            "",
            "## Animal and Translational Evidence",
            "",
            f"- Human evidence count: {audit.get('human_evidence_count', 0)}",
            f"- Animal evidence count: {audit.get('animal_evidence_count', 0)}",
            f"- Translational evidence count: {audit.get('translational_evidence_count', 0)}",
            f"- Species distribution: {audit.get('species_counts', {})}",
            f"- Evidence context distribution: {audit.get('evidence_context_counts', {})}",
            f"- Downstream role distribution: {audit.get('downstream_role_counts', {})}",
            f"- Translational risks: {dict(Counter(risk for item in evidence for risk in item.translational_risk))}",
            "- Animal evidence is used for mechanistic plausibility, not direct human clinical support.",
            "",
            "## LLM-assisted Evidence Verification",
            "",
            f"- LLM enabled: {llm.get('enabled', False)}",
            f"- Provider: {llm.get('provider', '')}",
            f"- Model: {llm.get('model', '')}",
            f"- LLM calls attempted: {llm.get('calls_attempted', 0)}",
            f"- LLM calls succeeded: {llm.get('calls_succeeded', 0)}",
            f"- LLM calls failed: {llm.get('calls_failed', 0)}",
            f"- Rule-only evidence count: {sum(1 for item in evidence if not item.llm_verified)}",
            f"- LLM-verified evidence count: {sum(1 for item in evidence if item.llm_verified)}",
            f"- LLM-revised evidence count: {llm.get('revised_evidence_count', 0)}",
            f"- LLM split claim count: {llm.get('split_claim_count', 0)}",
            f"- LLM excluded claim count: {llm.get('excluded_claim_count', 0)}",
            f"- Excluded evidence log: {llm.get('excluded_evidence_log', output_grounding / 'excluded_evidence_log.jsonl')}",
            f"- Failure fallback used: {llm.get('failure_fallback_used', False)}",
            "",
            "## Evidence Extraction Benchmark",
            "",
            f"- Mode: {benchmark.get('mode', 'not_run')}",
            f"- Mechanism recall: {benchmark.get('mechanism_recall', 0)}",
            f"- Mechanism precision: {benchmark.get('mechanism_precision', 0)}",
            f"- Direction accuracy: {benchmark.get('direction_accuracy', 0)}",
            f"- Modality accuracy: {benchmark.get('modality_accuracy', 0)}",
            f"- Species accuracy: {benchmark.get('species_accuracy', 0)}",
            f"- Evidence context accuracy: {benchmark.get('evidence_context_accuracy', 0)}",
            f"- Downstream role accuracy: {benchmark.get('downstream_role_accuracy', 0)}",
            f"- Paper coverage: {benchmark.get('paper_coverage', 0)}",
            f"- Hallucinated evidence count: {benchmark.get('hallucinated_evidence_count', 0)}",
            "",
            "## Scientific Loop Input Files",
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
