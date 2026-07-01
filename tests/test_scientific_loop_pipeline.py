from pathlib import Path

from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline


def test_scientific_loop_pipeline_generates_outputs():
    run_hypothesis_pipeline("configs/hypothesis_config.yaml")
    result = run_experiment_pipeline("configs/experiment_config.yaml")
    assert Path("outputs/hypotheses/hypothesis_pool.json").exists()
    assert Path("outputs/hypotheses/top_k_hypotheses.json").exists()
    assert list(Path("outputs/experiments/locked_plans").glob("*_locked_plan.json"))
    assert result["results"]
    assert result["reviews"]
    assert Path("reports/scientific_loop_report.md").exists()
