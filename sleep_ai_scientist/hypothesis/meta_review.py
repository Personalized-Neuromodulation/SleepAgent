from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.hypothesis.registry import dump_hypothesis
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, MetaReview, RankingResult, ReflectionReview


def build_meta_review(
    hypotheses: list[HypothesisRecord],
    reviews: list[ReflectionReview],
    ranking_results: list[RankingResult],
    config: dict[str, Any],
) -> tuple[MetaReview, list[HypothesisRecord]]:
    top_k = int(config.get("meta_review", {}).get("top_k", 10))
    by_id = {item.hypothesis_id: item for item in hypotheses}
    reviews_by_id = {item.hypothesis_id: item for item in reviews}
    ranked_ids = [item.hypothesis_id for item in sorted(ranking_results, key=lambda x: x.final_rank) if item.final_rank < 9999]
    eligible = [by_id[item] for item in ranked_ids if item in by_id and reviews_by_id.get(item, None) and reviews_by_id[item].recommendation != "reject"]
    top = eligible[:top_k]
    rejected = [item.hypothesis_id for item in reviews if item.recommendation == "reject"]
    revised = [item.hypothesis_id for item in reviews if item.recommendation == "revise"]
    themes = []
    for item in top:
        if item.mechanism not in themes:
            themes.append(item.mechanism)
    evidence_gaps = sorted({gap for review in reviews for gap in review.missing_evidence})
    data_gaps = sorted({var for review in reviews for var in review.unsupported_variables})
    recommended = [
        {
            "hypothesis_id": item.hypothesis_id,
            "title": item.title,
            "suggested_input": "outputs/co_scientist/co_scientist_top_k.json",
            "analysis_models": item.analysis_models,
        }
        for item in top
    ]
    meta = MetaReview(
        review_id="META_PHASE3_001",
        top_hypotheses=[item.hypothesis_id for item in top],
        rejected_hypotheses=rejected,
        revised_hypotheses=revised,
        major_themes=themes,
        evidence_gaps=evidence_gaps,
        data_gaps=data_gaps,
        recommended_next_experiments=recommended,
        summary="Deterministic Co-Scientist MVP ranked hypotheses using evidence, data grounding, reflection, diversity, and Elo tournament results.",
    )
    return meta, top


def write_meta_review(meta: MetaReview, top: list[HypothesisRecord], config: dict[str, Any]) -> dict[str, str]:
    root = Path(config["_project_root"])
    outputs = config.get("outputs", {})
    top_path = resolve_path(outputs["co_scientist_top_k"], root)
    meta_path = resolve_path(outputs["meta_review_report"], root)
    co_scientist_report_path = resolve_path(outputs["co_scientist_report"], root)
    write_json(top_path, [dump_hypothesis(item) for item in top])
    lines = [
        "# Co-Scientist Meta Review",
        "",
        "## Final Top Hypotheses",
        *[f"- {item.hypothesis_id}: {item.title} ({item.mechanism})" for item in top],
        "",
        "## Major Themes",
        *[f"- {item}" for item in meta.major_themes],
        "",
        "## Evidence Gaps",
        *[f"- {item}" for item in meta.evidence_gaps or ["No major evidence gap detected in linked candidate records."]],
        "",
        "## Data Gaps",
        *[f"- {item}" for item in meta.data_gaps or ["No unsupported analysis-ready variables in final candidates."]],
        "",
        "## Recommended Next Experiments",
        *[f"- {item['hypothesis_id']}: use {item['suggested_input']}" for item in meta.recommended_next_experiments],
        "",
        meta.summary,
    ]
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    co_scientist_report_path.parent.mkdir(parents=True, exist_ok=True)
    co_scientist_report_path.write_text("\n".join(["# Co-Scientist Report", "", *lines[2:]]) + "\n", encoding="utf-8")
    return {"co_scientist_top_k": str(top_path), "meta_review_report": str(meta_path), "co_scientist_report": str(co_scientist_report_path)}


def run_meta_review_agent(
    hypotheses: list[HypothesisRecord],
    reviews: list[ReflectionReview],
    ranking_results: list[RankingResult],
    config: dict[str, Any],
) -> dict[str, Any]:
    meta, top = build_meta_review(hypotheses, reviews, ranking_results, config)
    paths = write_meta_review(meta, top, config)
    return {"meta_review": meta, "top_hypotheses": top, "paths": paths}
