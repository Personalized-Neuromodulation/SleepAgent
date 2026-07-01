from pathlib import Path

from sleep_ai_scientist.hypothesis.co_scientist_pipeline import run_co_scientist_pipeline
from sleep_ai_scientist.common.io import read_json


def test_co_scientist_pipeline_generates_required_outputs():
    result = run_co_scientist_pipeline("configs/co_scientist_config.yaml")
    required = [
        "outputs/co_scientist/candidate_pool.json",
        "outputs/co_scientist/hypothesis_embeddings.csv",
        "outputs/co_scientist/proximity_clusters.json",
        "outputs/co_scientist/reflection_reviews.json",
        "outputs/co_scientist/ranking_pairs.json",
        "outputs/co_scientist/ranking_results.csv",
        "outputs/co_scientist/evolved_hypotheses.json",
        "outputs/co_scientist/meta_review_report.md",
        "outputs/co_scientist/co_scientist_top_k.json",
        "reports/co_scientist_report.md",
    ]
    assert result["candidate_count"] > 0
    for path in required:
        assert Path(path).exists()
    top = read_json(Path("outputs/co_scientist/co_scientist_top_k.json"))
    assert top
    assert {"hypothesis_id", "variables", "used_data_features"} <= set(top[0])
