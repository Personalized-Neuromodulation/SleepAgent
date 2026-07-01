from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.experiment.plan_lock import lock_draft_plans, plan_hash
from sleep_ai_scientist.experiment.planner import create_draft_plans
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline


def test_plan_lock_sets_hash_and_status():
    run_hypothesis_pipeline("configs/hypothesis_config.yaml")
    config = load_config("configs/experiment_config.yaml")
    create_draft_plans(config)
    locked = lock_draft_plans(config)
    assert locked
    assert all(item["lock_status"] == "locked" for item in locked)
    assert locked[0]["plan_hash"] == plan_hash(locked[0])

