from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import load_config, resolve_path
from sleep_ai_scientist.common.io import read_json
from sleep_ai_scientist.experiment.critic import run_critic_agent
from sleep_ai_scientist.experiment.plan_lock import lock_draft_plans
from sleep_ai_scientist.experiment.planner import create_draft_plans
from sleep_ai_scientist.experiment.result_updater import update_results_into_registry
from sleep_ai_scientist.experiment.robustness import run_robustness_agent
from sleep_ai_scientist.experiment.stats_agent import run_stats_agent


def generate_scientific_loop_report(config: dict[str, Any], summary: dict[str, Any] | None = None) -> str:
    root = Path(config["_project_root"])
    report_path = resolve_path(config.get("outputs", {})["report"], root)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    top_path = resolve_path(config.get("inputs", {})["top_k_hypotheses"], root)
    top = read_json(top_path) if top_path.exists() else []
    lines = [
        "# Scientific Loop Report",
        "",
        "## Inputs",
        f"- top_k_hypotheses: {top_path}",
        f"- master_table: {resolve_path(config.get('inputs', {})['master_table'], root)}",
        "",
        "## Top Hypotheses",
    ]
    for item in top:
        lines.append(f"- {item.get('hypothesis_id')}: {item.get('title')} (score={item.get('pre_analysis_score')})")
    lines.extend(["", "## Experiments"])
    for result in (summary or {}).get("results", []):
        predictor_terms = {k: result.get("corrected_p_values", {}).get(k) for k in result.get("effect_sizes", {})}
        lines.append(f"- {result['experiment_id']}: n_used={result.get('n_used')}, corrected_p={predictor_terms}")
    lines.extend(["", "## Critic Decisions"])
    for review in (summary or {}).get("reviews", []):
        lines.append(f"- {review['experiment_id']}: {review.get('decision')} / {review.get('claim_strength')}")
    lines.extend(
        [
            "",
            "## Co-Scientist Inputs",
            "- outputs/hypotheses/hypothesis_registry.csv",
            "- outputs/hypotheses/hypothesis_lineage.json",
            "- outputs/experiments/results/",
            "- outputs/experiments/critic_reviews/",
            "- outputs/memory/null_findings_registry.csv",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(report_path)


def run_experiment_pipeline(config_path: str = "configs/experiment_config.yaml") -> dict[str, Any]:
    config = load_config(config_path)
    plans = create_draft_plans(config)
    locked = lock_draft_plans(config)
    results = run_stats_agent(config)
    robustness = run_robustness_agent(config)
    reviews = run_critic_agent(config)
    updates = update_results_into_registry(config, reviews, results)
    report = generate_scientific_loop_report(config, {"results": results, "reviews": reviews})
    return {
        "draft_plans": len(plans),
        "locked_plans": len([item for item in locked if item.get("lock_status") == "locked"]),
        "results": results,
        "robustness": robustness,
        "reviews": reviews,
        "updates": updates,
        "report": report,
    }
