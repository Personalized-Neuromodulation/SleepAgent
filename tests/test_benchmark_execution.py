from pathlib import Path

from sleep_ai_scientist.benchmark.execution_benchmark import run_execution_benchmark
from sleep_ai_scientist.common.config import load_config


def test_execution_benchmark_scores_existing_locked_plans():
    config = load_config("configs/benchmark_config.yaml")
    scores = run_execution_benchmark(config)
    assert scores
    assert scores[0].has_locked_plan is True
    assert scores[0].result_file_exists is True
    assert Path("outputs/benchmark/execution_benchmark_scores.csv").exists()

