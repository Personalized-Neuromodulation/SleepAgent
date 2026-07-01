from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline


def test_robustness_outputs_structure():
    run_hypothesis_pipeline("configs/hypothesis_config.yaml")
    result = run_experiment_pipeline("configs/experiment_config.yaml")
    robustness = result["robustness"][0]
    assert "bootstrap_summary" in robustness
    assert "permutation_summary" in robustness
    assert "passed" in robustness

