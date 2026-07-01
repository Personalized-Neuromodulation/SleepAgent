from pathlib import Path

from sleep_ai_scientist.benchmark.expert_review import generate_expert_review_template, run_expert_review
from sleep_ai_scientist.common.config import load_config


def test_expert_review_template_generated_when_no_ratings_required():
    config = load_config("configs/benchmark_config.yaml")
    template = generate_expert_review_template(config)
    assert Path(template).exists()
    result = run_expert_review(config)
    assert "expert_evaluation_pending" in result

