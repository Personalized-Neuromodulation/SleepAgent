from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.experiment.agents.llm import build_experiment_llm, load_prompt
from sleep_ai_scientist.schemas.experiment import CriticFinding, ExperimentResultBundle


class ResultReviewAgent:
    """Uses LLM scientific review to judge support, confounds, and interpretability."""

    def __init__(self, config: dict[str, Any], *, output_dir: str | Path) -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.llm = build_experiment_llm(
            config.get("llm", {}),
            task_name="ResultReviewAgent: judge support, confounds, and feedback",
        )

    def run(self, bundle: ExperimentResultBundle) -> tuple[list[CriticFinding], dict[str, Any]]:
        review = self._llm_review(bundle) if self.llm else self._llm_required_review(bundle)
        findings = [
            CriticFinding(
                severity=str(item.get("severity", "medium")),
                category=str(item.get("category", "llm_review")),
                message=str(item.get("message", "")),
                recommendation=str(item.get("recommendation", "")),
            )
            for item in review.get("critic_findings", [])
            if isinstance(item, dict)
        ]
        if not findings and review.get("status") == "requires_llm_review":
            findings.append(
                CriticFinding(
                    severity="medium",
                    category="llm_review_required",
                    message="Numerical experiment completed, but scientific result judgment requires LLM review.",
                    recommendation="Enable online or Ollama LLM before treating support/reward as scientific evidence.",
                )
            )
        evidence_update = {
            "hypothesis_id": bundle.plan.hypothesis_id,
            "plan_id": bundle.plan.plan_id,
            "review_status": review.get("judgment", review.get("status", "reviewed")),
            "support_score": float(review.get("support_score", 0.5)),
            "result_review": review,
            "primary_tests": [test.model_dump() for test in bundle.stats_result.tests] if bundle.stats_result else [],
            "robustness_results": [item.model_dump() for item in bundle.robustness_results],
            "negative_control_results": [item.model_dump() for item in bundle.negative_control_results],
        }
        write_json(self.output_dir / f"{bundle.plan.plan_id}.result_review.json", evidence_update)
        return findings, evidence_update

    def _llm_review(self, bundle: ExperimentResultBundle) -> dict[str, Any]:
        system, user, max_tokens = load_prompt(
            "result_review",
            "review_results",
            {"bundle_json": json.dumps(bundle.model_dump(), ensure_ascii=False, indent=2)},
        )
        return self.llm.call_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=float(self.config.get("llm", {}).get("temperature", 0.1)),
        )

    def _llm_required_review(self, bundle: ExperimentResultBundle) -> dict[str, Any]:
        return {
            "status": "requires_llm_review",
            "judgment": "not_adjudicated",
            "support_score": 0.5,
            "critic_findings": [],
            "reason": "Rules for support scoring were removed; LLM review is required to judge support, confounds, and alternatives.",
        }
