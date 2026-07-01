from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_json, write_json
from sleep_ai_scientist.schemas.result import CriticReview


def review_experiment(hypothesis: dict[str, Any] | None, plan: dict[str, Any], result: dict[str, Any], robustness: dict[str, Any], config: dict[str, Any]) -> CriticReview:
    concerns: list[str] = []
    if result.get("status") != "ok":
        concerns.append("analysis_failed")
    if int(result.get("n_used", 0)) < int(plan.get("quality_gates", {}).get("min_n_total", 20)):
        concerns.append("sample_size_below_gate")
    if not result.get("effect_sizes"):
        concerns.append("missing_effect_size")
    if not result.get("corrected_p_values"):
        concerns.append("missing_corrected_p_value")
    if not robustness.get("passed", False):
        concerns.extend(robustness.get("warnings", []))
    if any(name in plan.get("predictors", []) + plan.get("covariates", []) for name in ["mean_FD", "in_scanner_sleep_time", "medication"]):
        concerns.append("key_confound_review_required")
    corrected = [value for key, value in result.get("corrected_p_values", {}).items() if key in plan.get("predictors", [])]
    has_signal = bool(corrected) and min(corrected) < 0.05
    if "analysis_failed" in concerns:
        decision = "hold"
    elif has_signal and robustness.get("passed", False) and len(concerns) <= 1:
        decision = "accepted"
    elif has_signal:
        decision = "revised"
    elif int(result.get("n_used", 0)) < int(plan.get("quality_gates", {}).get("min_n_total", 20)):
        decision = "hold"
    else:
        decision = "rejected"
    claim = "robust_association" if decision == "accepted" else "exploratory_association" if decision == "revised" else "not_supported"
    strength = "strong" if decision == "accepted" else "moderate" if decision == "revised" else "weak"
    return CriticReview(
        experiment_id=plan["experiment_id"],
        hypothesis_id=plan["hypothesis_id"],
        decision=decision,
        evidence_strength=strength,
        claim_strength=claim,
        main_concerns=concerns,
        required_followups=["replicate in larger sample", "confirm confound control"] if decision in {"accepted", "revised"} else ["increase usable sample size", "review variable availability"],
        causal_language_allowed=False,
        summary=f"Decision={decision}; claim_strength={claim}; causal language is not allowed in the scientific loop.",
    )


def run_critic_agent(config: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(config["_project_root"])
    outputs = config.get("outputs", {})
    inputs = config.get("inputs", {})
    top_path = resolve_path(inputs["top_k_hypotheses"], root)
    hypotheses = {item["hypothesis_id"]: item for item in read_json(top_path)} if top_path.exists() else {}
    locked_dir = resolve_path(outputs["locked_plans_dir"], root)
    results_dir = resolve_path(outputs["results_dir"], root)
    robustness_dir = resolve_path(outputs["robustness_dir"], root)
    review_dir = resolve_path(outputs["critic_reviews_dir"], root)
    review_dir.mkdir(parents=True, exist_ok=True)
    reviews = []
    for result_path in sorted(results_dir.glob("*_result.json")):
        result = read_json(result_path)
        plan = read_json(locked_dir / f"{result['experiment_id']}_locked_plan.json")
        robustness = read_json(robustness_dir / f"{result['experiment_id']}_robustness.json")
        review = review_experiment(hypotheses.get(result["hypothesis_id"]), plan, result, robustness, config)
        payload = review.model_dump(mode="json")
        write_json(review_dir / f"{review.experiment_id}_critic_review.json", payload)
        md = [
            f"# Critic Review: {review.experiment_id}",
            "",
            f"- Hypothesis: {review.hypothesis_id}",
            f"- Decision: {review.decision}",
            f"- Evidence strength: {review.evidence_strength}",
            f"- Claim strength: {review.claim_strength}",
            f"- Causal language allowed: {review.causal_language_allowed}",
            "",
            "## Concerns",
            *[f"- {item}" for item in review.main_concerns],
            "",
            review.summary,
        ]
        (review_dir / f"{review.experiment_id}_critic_review.md").write_text("\n".join(md), encoding="utf-8")
        reviews.append(payload)
    return reviews
