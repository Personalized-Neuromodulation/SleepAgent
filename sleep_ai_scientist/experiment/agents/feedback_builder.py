from __future__ import annotations

from typing import Any

from sleep_ai_scientist.schemas.experiment import ExperimentResultBundle


def build_experimental_feedback(bundle: ExperimentResultBundle) -> dict[str, Any]:
    update = bundle.evidence_update or {}
    status = str(update.get("review_status", "not_adjudicated"))
    support_score = float(update.get("support_score", 0.5))
    primary = bundle.stats_result.tests if bundle.stats_result else []
    passed = sum(1 for test in primary if test.passed)
    total = len(primary)
    robustness_passed = sum(1 for item in bundle.robustness_results if item.passed)
    negative_passed = sum(1 for item in bundle.negative_control_results if item.passed)

    if status == "requires_llm_review":
        reward = 0.0
    else:
        stats_component = passed / total if total else 0.0
        robustness_component = robustness_passed / len(bundle.robustness_results) if bundle.robustness_results else 0.5
        negative_component = negative_passed / len(bundle.negative_control_results) if bundle.negative_control_results else 0.5
        reward = round((0.55 * support_score) + (0.25 * stats_component) + (0.1 * robustness_component) + (0.1 * negative_component), 4)

    return {
        "hypothesis_id": bundle.plan.hypothesis_id,
        "plan_id": bundle.plan.plan_id,
        "support": status,
        "support_score": support_score,
        "computed_reward": reward,
        "validated": bool(reward >= 0.7),
        "refuted": bool(reward <= 0.25 and status != "requires_llm_review"),
        "primary_tests_passed": passed,
        "primary_tests_total": total,
        "metadata": {
            "review_status": status,
            "hypothesis_title": bundle.plan.hypothesis_title,
            "predictors": bundle.plan.predictors,
            "outcomes": bundle.plan.outcomes,
            "critic_findings": [finding.model_dump() for finding in bundle.critic_findings],
        },
    }
