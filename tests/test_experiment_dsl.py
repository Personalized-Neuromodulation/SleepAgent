from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.hypothesis.generator import generate_candidate_hypotheses
from sleep_ai_scientist.experiment.experiment_dsl import hypothesis_to_plan


def test_hypothesis_record_to_experiment_plan():
    h_config = load_config("configs/hypothesis_config.yaml")
    e_config = load_config("configs/experiment_config.yaml")
    hypothesis = generate_candidate_hypotheses(h_config)[0]
    plan = hypothesis_to_plan(hypothesis, e_config)
    assert plan.hypothesis_id == hypothesis.hypothesis_id
    assert plan.outcome in plan.model_formula
    assert plan.lock_status == "draft" or getattr(plan.lock_status, "value", "") == "draft"
