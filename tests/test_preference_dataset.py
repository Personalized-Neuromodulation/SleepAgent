from pathlib import Path

from sleep_ai_scientist.benchmark.preference_dataset import run_preference_dataset
from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.schemas.benchmark import HypothesisQualityScore


def _quality(hid: str, score: float) -> HypothesisQualityScore:
    return HypothesisQualityScore(
        hypothesis_id=hid,
        valid_variables=True,
        has_supporting_evidence=True,
        has_falsification_criteria=True,
        has_analysis_model=True,
        evidence_level="exploratory",
        status="screened",
        mechanism_plausibility_score=score,
        data_testability_score=score,
        evidence_grounding_score=score,
        falsifiability_score=score,
        novelty_proxy_score=score,
        clinical_value_score=score,
        overclaim_risk_score=0,
        overall_quality_score=score,
    )


def test_rule_based_pairwise_preferences_jsonl():
    config = load_config("configs/benchmark_config.yaml")
    prefs = run_preference_dataset(config, [], [_quality("H1", 0.9), _quality("H2", 0.3)])
    assert prefs[0].source == "rule_based"
    assert Path("outputs/benchmark/pairwise_preferences.jsonl").exists()

