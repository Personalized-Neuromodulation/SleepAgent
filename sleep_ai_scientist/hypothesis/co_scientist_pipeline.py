from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import load_config, resolve_path
from sleep_ai_scientist.common.io import read_csv, read_json, write_csv, write_json
from sleep_ai_scientist.hypothesis.evolution import evolved_to_hypothesis, run_evolution_agent
from sleep_ai_scientist.hypothesis.generator import generate_candidate_hypotheses
from sleep_ai_scientist.hypothesis.meta_review import run_meta_review_agent
from sleep_ai_scientist.hypothesis.proximity import hypothesis_from_dict, run_proximity_agent
from sleep_ai_scientist.hypothesis.ranking import run_ranking_agent
from sleep_ai_scientist.hypothesis.reflection import run_reflection_agent
from sleep_ai_scientist.hypothesis.registry import dump_hypothesis
from sleep_ai_scientist.hypothesis.scorer import score_hypotheses
from sleep_ai_scientist.memory.scientific_memory import append_event
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord


def _load_scientific_loop_pool(config: dict[str, Any]) -> list[HypothesisRecord]:
    root = Path(config["_project_root"])
    path = resolve_path(config.get("inputs", {}).get("hypothesis_pool", "outputs/hypotheses/hypothesis_pool.json"), root)
    if not path.exists():
        return []
    return [hypothesis_from_dict(item) for item in read_json(path)]


def _dedupe(hypotheses: list[HypothesisRecord]) -> list[HypothesisRecord]:
    seen: set[str] = set()
    output: list[HypothesisRecord] = []
    for hypothesis in hypotheses:
        if hypothesis.hypothesis_id in seen:
            continue
        seen.add(hypothesis.hypothesis_id)
        output.append(hypothesis)
    return output


def _append_evolved_to_registry_and_lineage(evolved: list[HypothesisRecord], config: dict[str, Any]) -> dict[str, int]:
    root = Path(config["_project_root"])
    inputs = config.get("inputs", {})
    registry_path = resolve_path(inputs.get("hypothesis_registry", "outputs/hypotheses/hypothesis_registry.csv"), root)
    lineage_path = resolve_path(inputs.get("hypothesis_lineage", "outputs/hypotheses/hypothesis_lineage.json"), root)
    rows = read_csv(registry_path) if registry_path.exists() else []
    existing_ids = {row.get("hypothesis_id") for row in rows}
    added_rows = 0
    for hypothesis in evolved:
        if hypothesis.hypothesis_id in existing_ids:
            continue
        rows.append(
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "title": hypothesis.title,
                "mechanism": hypothesis.mechanism,
                "status": hypothesis.status.value if hasattr(hypothesis.status, "value") else hypothesis.status,
                "evidence_level": hypothesis.evidence_level.value if hasattr(hypothesis.evidence_level, "value") else hypothesis.evidence_level,
                "pre_analysis_score": hypothesis.pre_analysis_score,
                "parent_id": hypothesis.parent_id or "",
                "used_data_features": ";".join(hypothesis.used_data_features),
            }
        )
        existing_ids.add(hypothesis.hypothesis_id)
        added_rows += 1
    if rows:
        write_csv(registry_path, rows)

    lineage = read_json(lineage_path) if lineage_path.exists() else {"nodes": [], "edges": []}
    node_ids = {node.get("hypothesis_id") for node in lineage.get("nodes", [])}
    edge_keys = {(edge.get("parent_id"), edge.get("child_id")) for edge in lineage.get("edges", [])}
    added_nodes = 0
    added_edges = 0
    for hypothesis in evolved:
        if hypothesis.hypothesis_id not in node_ids:
            lineage.setdefault("nodes", []).append(
                {
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "parent_id": hypothesis.parent_id,
                    "status": hypothesis.status.value if hasattr(hypothesis.status, "value") else hypothesis.status,
                    "evidence_level": hypothesis.evidence_level.value if hasattr(hypothesis.evidence_level, "value") else hypothesis.evidence_level,
                    "source": hypothesis.source,
                }
            )
            node_ids.add(hypothesis.hypothesis_id)
            added_nodes += 1
        if hypothesis.parent_id and (hypothesis.parent_id, hypothesis.hypothesis_id) not in edge_keys:
            lineage.setdefault("edges", []).append({"parent_id": hypothesis.parent_id, "child_id": hypothesis.hypothesis_id})
            edge_keys.add((hypothesis.parent_id, hypothesis.hypothesis_id))
            added_edges += 1
    write_json(lineage_path, lineage)
    return {"registry_rows_added": added_rows, "lineage_nodes_added": added_nodes, "lineage_edges_added": added_edges}


def build_candidate_pool(config: dict[str, Any]) -> list[HypothesisRecord]:
    candidates: list[HypothesisRecord] = []
    if config.get("generation", {}).get("include_scientific_loop_pool", True):
        candidates.extend(_load_scientific_loop_pool(config))
    generated = generate_candidate_hypotheses(config)
    candidates.extend(generated)
    candidates = score_hypotheses(_dedupe(candidates), config)
    max_candidates = int(config.get("generation", {}).get("max_candidates", 80))
    return sorted(candidates, key=lambda item: item.pre_analysis_score or 0.0, reverse=True)[:max_candidates]


def run_co_scientist_pipeline(config_path: str = "configs/co_scientist_config.yaml") -> dict[str, Any]:
    config = load_config(config_path)
    root = Path(config["_project_root"])
    outputs = config.get("outputs", {})
    resolve_path(outputs["co_scientist_dir"], root).mkdir(parents=True, exist_ok=True)

    candidates = build_candidate_pool(config)
    write_json(resolve_path(outputs["candidate_pool"], root), [dump_hypothesis(item) for item in candidates])
    append_event("co_scientist_candidate_generated", {"candidate_count": len(candidates)})

    proximity = run_proximity_agent(candidates, config)
    append_event("proximity_clustered", {"cluster_count": len(proximity["clusters"])})

    reviews = run_reflection_agent(candidates, config)
    append_event("reflection_reviewed", {"review_count": len(reviews)})

    pairs, ranking_results = run_ranking_agent(candidates, reviews, proximity["representative_ids"], config)
    append_event("ranking_completed", {"pair_count": len(pairs), "ranked_count": len(ranking_results)})

    evolved = run_evolution_agent(candidates, reviews, ranking_results, config)
    evolved_as_hypotheses = [evolved_to_hypothesis(item, {h.hypothesis_id: h for h in candidates}.get(item.parent_ids[0])) for item in evolved]
    lineage_updates = _append_evolved_to_registry_and_lineage(evolved_as_hypotheses, config)
    append_event("hypothesis_evolved", {"evolved_count": len(evolved)})

    all_candidates = _dedupe(candidates + score_hypotheses(evolved_as_hypotheses, config))
    if evolved_as_hypotheses:
        reviews = run_reflection_agent(all_candidates, config)
        proximity = run_proximity_agent(all_candidates, config)
        pairs, ranking_results = run_ranking_agent(all_candidates, reviews, proximity["representative_ids"], config)

    meta = run_meta_review_agent(all_candidates, reviews, ranking_results, config)
    append_event("meta_review_completed", {"top_k": len(meta["top_hypotheses"])})
    return {
        "candidate_pool": str(resolve_path(outputs["candidate_pool"], root)),
        "candidate_count": len(candidates),
        "cluster_count": len(proximity["clusters"]),
        "reflection_count": len(reviews),
        "ranking_pair_count": len(pairs),
        "evolved_count": len(evolved),
        "lineage_updates": lineage_updates,
        "co_scientist_top_k": meta["paths"]["co_scientist_top_k"],
        "meta_review_report": meta["paths"]["meta_review_report"],
        "co_scientist_report": meta["paths"]["co_scientist_report"],
    }


def generate_co_scientist_report(config_path: str = "configs/co_scientist_config.yaml") -> dict[str, str]:
    config = load_config(config_path)
    root = Path(config["_project_root"])
    return {
        "meta_review_report": str(resolve_path(config.get("outputs", {})["meta_review_report"], root)),
        "co_scientist_report": str(resolve_path(config.get("outputs", {})["co_scientist_report"], root)),
    }
