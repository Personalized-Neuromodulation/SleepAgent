from __future__ import annotations

from datetime import datetime
from typing import Any

from sleep_ai_scientist.benchmark.utils import output_path
from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.schemas.benchmark import BenchmarkSummary


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def build_summary(results: dict[str, Any], config: dict[str, Any]) -> BenchmarkSummary:
    hq = results.get("hypothesis_quality", [])
    grounding = results.get("grounding", [])
    execution = results.get("execution", [])
    critic = results.get("critic", [])
    repro = results.get("reproducibility", [])
    co = results.get("co_scientist", [])
    valid_rate = mean([1.0 if item.valid_variables else 0.0 for item in hq])
    grounding_rate = mean([1.0 if item.grounding_passed else 0.0 for item in grounding])
    executable_rate = mean([1.0 if item.execution_success else 0.0 for item in execution])
    agreement_values = [item.agreement_score for item in critic if item.agreement_score is not None]
    critic_agreement = mean(agreement_values) if agreement_values else None
    mean_quality = mean([item.overall_quality_score for item in hq])
    mean_repro = mean([item.reproducibility_score for item in repro])
    co_improvement = mean([item.improvement_over_scientific_loop_score for item in co]) if co else None
    thresholds = config.get("benchmark", {})
    failed = []
    if valid_rate < float(thresholds.get("minimum_valid_hypothesis_rate", 0.8)):
        failed.append("valid_hypothesis_rate")
    if grounding_rate < float(thresholds.get("minimum_data_grounding_rate", 0.9)):
        failed.append("data_grounding_rate")
    if executable_rate < float(thresholds.get("minimum_executable_plan_rate", 0.7)):
        failed.append("executable_plan_rate")
    if mean_repro < float(thresholds.get("minimum_reproducibility_score", 0.8)):
        failed.append("reproducibility_score")
    recommendations = []
    if failed:
        recommendations.append("Review failed benchmark dimensions before using outputs for downstream learning.")
    if not results.get("expert_ratings"):
        recommendations.append("Collect expert_ratings.csv before preference learning.")
    return BenchmarkSummary(
        total_hypotheses=len(hq),
        valid_hypothesis_rate=valid_rate,
        data_grounding_rate=grounding_rate,
        executable_plan_rate=executable_rate,
        critic_expert_agreement=critic_agreement,
        mean_hypothesis_quality_score=mean_quality,
        mean_reproducibility_score=mean_repro,
        co_scientist_improvement_score=co_improvement,
        passed=not failed,
        failed_checks=failed,
        recommendations=recommendations,
    )


def write_benchmark_report(config: dict[str, Any], results: dict[str, Any], summary: BenchmarkSummary) -> dict[str, str]:
    write_json(output_path(config, "benchmark_summary"), summary.model_dump(mode="json"))
    lines = [
        "# Benchmark + Expert Review Report",
        "",
        f"- Project: {config.get('project', {}).get('name', 'SleepAgent')}",
        f"- Run time: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Hypothesis Benchmark",
        f"- Total hypotheses: {summary.total_hypotheses}",
        f"- Valid hypothesis rate: {summary.valid_hypothesis_rate}",
        f"- Mean quality score: {summary.mean_hypothesis_quality_score}",
        "",
        "## Grounding Benchmark",
        f"- Data grounding rate: {summary.data_grounding_rate}",
        "",
        "## Execution Benchmark",
        f"- Executable plan rate: {summary.executable_plan_rate}",
        "",
        "## Critic Benchmark",
        f"- Critic reviews: {len(results.get('critic', []))}",
        f"- Critic-expert agreement: {summary.critic_expert_agreement}",
        "",
        "## Co-Scientist Benchmark",
        f"- Co-Scientist rows: {len(results.get('co_scientist', []))}",
        f"- Improvement score: {summary.co_scientist_improvement_score}",
        "",
        "## Reproducibility Benchmark",
        f"- Mean reproducibility score: {summary.mean_reproducibility_score}",
        "",
        "## Expert Review",
        f"- Expert ratings: {len(results.get('expert_ratings', []))}",
        f"- Template generated: {results.get('expert_template')}",
        "",
        "## Preference Dataset",
        f"- Pairwise preferences: {len(results.get('preferences', []))}",
        "",
        "## Overall System Readiness",
        f"- Passed: {summary.passed}",
        f"- Failed checks: {', '.join(summary.failed_checks) if summary.failed_checks else 'none'}",
        "",
        "## Recommendations",
        *[f"- {item}" for item in summary.recommendations],
    ]
    benchmark_report = output_path(config, "benchmark_report")
    system_report = output_path(config, "system_benchmark_report")
    benchmark_report.parent.mkdir(parents=True, exist_ok=True)
    system_report.parent.mkdir(parents=True, exist_ok=True)
    benchmark_report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    system_report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"benchmark_report": str(benchmark_report), "system_benchmark_report": str(system_report)}
