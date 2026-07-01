from sleep_ai_scientist.hypothesis.meta_review import build_meta_review
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, HypothesisVariables, RankingResult, ReflectionReview


def test_meta_review_outputs_top_k_and_recommendations():
    hypothesis = HypothesisRecord(
        hypothesis_id="H001",
        title="Slow wave predicts ISI",
        mechanism="slow-wave generation",
        primary_prediction="test",
        variables=HypothesisVariables(independent=["slow_wave_density"], dependent=["ISI"], covariates=[]),
        used_data_features=["slow_wave_density", "ISI"],
    )
    review = ReflectionReview(hypothesis_id="H001", review_id="R1", recommendation="keep", overall_reflection_score=0.9)
    rank = RankingResult(hypothesis_id="H001", final_rank=1, elo_score=1510)
    meta, top = build_meta_review([hypothesis], [review], [rank], {"meta_review": {"top_k": 1}})
    assert meta.top_hypotheses == ["H001"]
    assert meta.major_themes == ["slow-wave generation"]
    assert meta.recommended_next_experiments
    assert top[0].hypothesis_id == "H001"

