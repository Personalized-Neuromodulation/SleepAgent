from sleep_ai_scientist.hypothesis.ranking import pairwise_rank
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, HypothesisVariables, ReflectionReview


def _hypothesis(hid: str, score: float) -> HypothesisRecord:
    return HypothesisRecord(
        hypothesis_id=hid,
        title=hid,
        mechanism="slow-wave generation",
        primary_prediction="test",
        variables=HypothesisVariables(independent=["slow_wave_density"], dependent=["ISI"], covariates=[]),
        used_data_features=["slow_wave_density", "ISI"],
        pre_analysis_score=score,
        score_components={"evidence_strength": score, "data_testability": score, "novelty_proxy": score, "confound_controllability": score},
        falsification_criteria=["No association."],
    )


def _review(hid: str, score: float, recommendation: str = "keep") -> ReflectionReview:
    return ReflectionReview(hypothesis_id=hid, review_id=f"R_{hid}", overall_reflection_score=score, recommendation=recommendation)


def test_pairwise_ranking_prefers_higher_grounded_score():
    high = _hypothesis("H_HIGH", 0.9)
    low = _hypothesis("H_LOW", 0.2)
    pairs, results = pairwise_rank([high, low], [_review("H_HIGH", 0.9), _review("H_LOW", 0.2)], {"H_HIGH", "H_LOW"}, {"ranking": {"initial_elo": 1500, "k_factor": 32}})
    assert pairs[0].winner == "H_HIGH"
    assert results[0].hypothesis_id == "H_HIGH"
    assert results[0].elo_score > 1500


def test_rejected_hypothesis_is_excluded_from_final_rank():
    high = _hypothesis("H_HIGH", 0.9)
    rejected = _hypothesis("H_REJECT", 0.95)
    _, results = pairwise_rank([high, rejected], [_review("H_HIGH", 0.9), _review("H_REJECT", 0.95, "reject")], None, {"ranking": {}})
    rejected_result = next(item for item in results if item.hypothesis_id == "H_REJECT")
    assert rejected_result.final_rank == 9999

