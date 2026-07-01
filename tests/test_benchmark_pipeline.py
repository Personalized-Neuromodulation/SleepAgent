from pathlib import Path

from sleep_ai_scientist.benchmark.benchmark_pipeline import run_benchmark_pipeline


def test_benchmark_pipeline_generates_outputs():
    result = run_benchmark_pipeline("configs/benchmark_config.yaml")
    required = [
        "outputs/benchmark/hypothesis_quality_scores.csv",
        "outputs/benchmark/grounding_benchmark_scores.csv",
        "outputs/benchmark/execution_benchmark_scores.csv",
        "outputs/benchmark/critic_benchmark_scores.csv",
        "outputs/benchmark/co_scientist_benchmark_scores.csv",
        "outputs/benchmark/reproducibility_scores.csv",
        "outputs/benchmark/expert_review_template.csv",
        "outputs/benchmark/pairwise_preferences.jsonl",
        "outputs/benchmark/benchmark_summary.json",
        "outputs/benchmark/benchmark_scores.csv",
        "outputs/benchmark/benchmark_report.md",
        "reports/benchmark_report.md",
    ]
    assert result["summary"]["total_hypotheses"] > 0
    for path in required:
        assert Path(path).exists()
