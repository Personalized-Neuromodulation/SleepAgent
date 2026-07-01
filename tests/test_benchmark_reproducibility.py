from sleep_ai_scientist.benchmark.reproducibility_benchmark import run_reproducibility_benchmark
from sleep_ai_scientist.common.config import load_config


def test_reproducibility_scores_required_artifacts():
    scores = run_reproducibility_benchmark(load_config("configs/benchmark_config.yaml"))
    assert scores
    assert all(score.reproducibility_score > 0 for score in scores)
    assert any(score.artifact_id == "grounding" for score in scores)

