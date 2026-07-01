from __future__ import annotations

from typing import Any

from sleep_ai_scientist.benchmark.benchmark_report import build_summary, write_benchmark_report
from sleep_ai_scientist.benchmark.co_scientist_benchmark import run_co_scientist_benchmark
from sleep_ai_scientist.benchmark.critic_benchmark import run_critic_benchmark
from sleep_ai_scientist.benchmark.execution_benchmark import run_execution_benchmark
from sleep_ai_scientist.benchmark.expert_review import run_expert_review
from sleep_ai_scientist.benchmark.grounding_benchmark import run_grounding_benchmark
from sleep_ai_scientist.benchmark.hypothesis_quality import run_hypothesis_quality_benchmark
from sleep_ai_scientist.benchmark.preference_dataset import run_preference_dataset
from sleep_ai_scientist.benchmark.reproducibility_benchmark import run_reproducibility_benchmark
from sleep_ai_scientist.benchmark.utils import model_dump_rows, output_path
from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.common.io import write_csv
from sleep_ai_scientist.memory.scientific_memory import append_event


def _score_rows(summary: Any) -> list[dict[str, Any]]:
    payload = summary.model_dump(mode="json")
    return [{"metric": key, "value": value} for key, value in payload.items() if not isinstance(value, list)]


def run_benchmark_pipeline(config_path: str = "configs/benchmark_config.yaml") -> dict[str, Any]:
    config = load_config(config_path)
    output_path(config, "benchmark_dir").mkdir(parents=True, exist_ok=True)
    append_event("benchmark_started", {"config": config_path})
    quality = run_hypothesis_quality_benchmark(config)
    append_event("hypothesis_quality_benchmark_completed", {"rows": len(quality)})
    grounding = run_grounding_benchmark(config)
    append_event("grounding_benchmark_completed", {"rows": len(grounding)})
    execution = run_execution_benchmark(config)
    append_event("execution_benchmark_completed", {"rows": len(execution)})
    critic = run_critic_benchmark(config)
    append_event("critic_benchmark_completed", {"rows": len(critic)})
    co_scientist = run_co_scientist_benchmark(config)
    append_event("co_scientist_benchmark_completed", {"rows": len(co_scientist)})
    reproducibility = run_reproducibility_benchmark(config)
    expert = run_expert_review(config)
    append_event("expert_review_template_generated", {"path": expert["template"], "ratings": len(expert["ratings"])})
    preferences = run_preference_dataset(config, expert["ratings"], quality)
    append_event("pairwise_preferences_generated", {"rows": len(preferences)})
    results = {
        "hypothesis_quality": quality,
        "grounding": grounding,
        "execution": execution,
        "critic": critic,
        "co_scientist": co_scientist,
        "reproducibility": reproducibility,
        "expert_ratings": expert["ratings"],
        "expert_template": expert["template"],
        "preferences": preferences,
    }
    summary = build_summary(results, config)
    write_csv(output_path(config, "benchmark_scores"), _score_rows(summary))
    paths = write_benchmark_report(config, results, summary)
    append_event("benchmark_completed", {"passed": summary.passed, "failed_checks": summary.failed_checks})
    return {
        "summary": summary.model_dump(mode="json"),
        "outputs": paths,
        "hypothesis_quality_rows": len(quality),
        "grounding_rows": len(grounding),
        "execution_rows": len(execution),
        "critic_rows": len(critic),
        "co_scientist_rows": len(co_scientist),
        "reproducibility_rows": len(reproducibility),
        "preference_rows": len(preferences),
    }


def generate_benchmark_report(config_path: str = "configs/benchmark_config.yaml") -> dict[str, str]:
    config = load_config(config_path)
    return {
        "benchmark_report": str(output_path(config, "benchmark_report")),
        "system_benchmark_report": str(output_path(config, "system_benchmark_report")),
    }
