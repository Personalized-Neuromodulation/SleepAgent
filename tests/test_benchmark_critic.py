from sleep_ai_scientist.benchmark.critic_benchmark import agreement_score, run_critic_benchmark
from sleep_ai_scientist.common.config import load_config


def test_critic_expert_agreement_rules():
    assert agreement_score("accepted", "accept") == 1.0
    assert agreement_score("exploratory_only", "revise") == 0.5
    assert agreement_score("accepted", "reject") == 0.0


def test_critic_benchmark_outputs_self_check_scores():
    scores = run_critic_benchmark(load_config("configs/benchmark_config.yaml"))
    assert scores
    assert all(score.critic_score >= 0 for score in scores)

