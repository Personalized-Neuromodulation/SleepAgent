from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.benchmark.utils import input_path, load_hypotheses, output_path
from sleep_ai_scientist.common.io import read_csv, write_csv
from sleep_ai_scientist.schemas.benchmark import ExpertRating

FIELDS = [
    "expert_id",
    "item_type",
    "item_id",
    "title_or_summary",
    "mechanism_plausibility",
    "data_testability",
    "evidence_grounding",
    "novelty",
    "clinical_value",
    "statistical_feasibility",
    "confound_risk",
    "overclaim_risk",
    "priority_for_analysis",
    "decision",
    "free_text_comment",
]


def generate_expert_review_template(config: dict[str, Any]) -> str:
    rows = []
    for hypothesis in load_hypotheses(config):
        rows.append(
            {
                "expert_id": "",
                "item_type": "hypothesis",
                "item_id": hypothesis.get("hypothesis_id", ""),
                "title_or_summary": hypothesis.get("title", ""),
            }
        )
    write_csv(output_path(config, "expert_review_template"), rows, FIELDS)
    return str(output_path(config, "expert_review_template"))


def load_expert_ratings(config: dict[str, Any]) -> list[ExpertRating]:
    path = input_path(config, "expert_ratings")
    if not path.exists():
        generate_expert_review_template(config)
        return []
    ratings = []
    for row in read_csv(path):
        if not row.get("expert_id") or not row.get("item_id"):
            continue
        payload = {key: (None if value == "" else value) for key, value in row.items()}
        for key in [
            "mechanism_plausibility",
            "data_testability",
            "evidence_grounding",
            "novelty",
            "clinical_value",
            "statistical_feasibility",
            "confound_risk",
            "overclaim_risk",
            "priority_for_analysis",
        ]:
            if payload.get(key) is not None:
                payload[key] = int(float(payload[key]))
        payload.pop("title_or_summary", None)
        ratings.append(ExpertRating(**payload))
    if ratings:
        write_csv(output_path(config, "expert_ratings"), [item.model_dump(mode="json") for item in ratings])
    return ratings


def run_expert_review(config: dict[str, Any]) -> dict[str, Any]:
    template = generate_expert_review_template(config)
    ratings = load_expert_ratings(config)
    return {"template": template, "ratings": ratings, "expert_evaluation_pending": len(ratings) == 0}
