from sleep_ai_scientist.benchmark.co_scientist_benchmark import run_co_scientist_benchmark
from sleep_ai_scientist.common.config import load_config


def test_co_scientist_benchmark_checks_evolved_parent_ids():
    scores = run_co_scientist_benchmark(load_config("configs/benchmark_config.yaml"))
    assert scores
    evolved = [score for score in scores if score.evolved]
    assert evolved
    assert all(score.parent_ids for score in evolved)

