from sleep_ai_scientist.hypothesis.proximity import cluster_hypotheses
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, HypothesisVariables


def _hypothesis(hid: str, title: str, mechanism: str) -> HypothesisRecord:
    return HypothesisRecord(
        hypothesis_id=hid,
        title=title,
        mechanism=mechanism,
        primary_prediction=f"{title} is associated with ISI.",
        variables=HypothesisVariables(independent=["slow_wave_density"], dependent=["ISI"], covariates=[]),
        used_data_features=["slow_wave_density", "ISI"],
        falsification_criteria=["No association after adjustment."],
        pre_analysis_score=0.8,
    )


def test_co_scientist_proximity_clusters_similar_hypotheses():
    hypotheses = [
        _hypothesis("H_A", "Slow-wave density association", "slow-wave generation"),
        _hypothesis("H_B", "Slow-wave density association", "slow-wave generation"),
        _hypothesis("H_C", "Thalamus connectivity bridge", "thalamocortical coupling"),
    ]
    clusters, _ = cluster_hypotheses(hypotheses, {"proximity": {"distance_threshold": 0.35}})
    cluster_sets = [set(item.hypothesis_ids) for item in clusters]
    assert any({"H_A", "H_B"} <= item for item in cluster_sets)
    assert all(item.representative_id for item in clusters)

