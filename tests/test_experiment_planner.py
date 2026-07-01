from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.experiment.planner import create_draft_plans
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline


def test_experiment_planner_creates_draft_plans():
    run_hypothesis_pipeline("configs/hypothesis_config.yaml")
    config = load_config("configs/experiment_config.yaml")
    plans = create_draft_plans(config)
    assert plans
    assert all("model_formula" in plan for plan in plans)

