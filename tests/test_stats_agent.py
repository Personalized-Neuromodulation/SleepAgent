from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.experiment.plan_lock import lock_draft_plans
from sleep_ai_scientist.experiment.planner import create_draft_plans
from sleep_ai_scientist.experiment.stats_agent import run_stats_agent
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline


def test_stats_agent_outputs_coefficients_and_p_values():
    run_hypothesis_pipeline("configs/hypothesis_config.yaml")
    config = load_config("configs/experiment_config.yaml")
    create_draft_plans(config)
    lock_draft_plans(config)
    results = run_stats_agent(config)
    assert results
    assert results[0]["coefficients"]
    assert results[0]["p_values"]
    assert results[0]["n_used"] > 0

