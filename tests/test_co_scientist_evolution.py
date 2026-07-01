from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.hypothesis.evolution import evolve_hypotheses
from sleep_ai_scientist.hypothesis.reflection import analysis_ready_variables
from sleep_ai_scientist.schemas.hypothesis import HypothesisRecord, HypothesisVariables, RankingResult, ReflectionReview


def _parent(hid: str, dependent: str = "ISI") -> HypothesisRecord:
    return HypothesisRecord(
        hypothesis_id=hid,
        title=f"{hid} title",
        mechanism="thalamocortical coupling",
        primary_prediction="test",
        variables=HypothesisVariables(independent=["thalamus_DMN_FC"], dependent=[dependent], covariates=["mean_FD"]),
        required_modalities=["fMRI", "scales"],
        used_data_features=["thalamus_DMN_FC", dependent, "mean_FD"],
        falsification_criteria=["No association."],
    )


def test_evolution_creates_parented_analysis_ready_hypotheses():
    config = load_config("configs/co_scientist_config.yaml")
    hypotheses = [_parent("H001"), _parent("H002", "PSQI")]
    reviews = [ReflectionReview(hypothesis_id="H001", review_id="R1", confound_risks=["medication"], recommendation="revise"), ReflectionReview(hypothesis_id="H002", review_id="R2", recommendation="keep")]
    ranks = [RankingResult(hypothesis_id="H001", final_rank=1), RankingResult(hypothesis_id="H002", final_rank=2)]
    evolved = evolve_hypotheses(hypotheses, reviews, ranks, config)
    ready = analysis_ready_variables(config)
    assert evolved
    assert all(item.parent_ids for item in evolved)
    assert {item.evolution_strategy for item in evolved} & {"refine", "merge", "mutate"}
    for item in evolved:
        used = item.variables.independent + item.variables.dependent + item.variables.covariates
        assert set(used) <= ready
        assert str(item.evidence_level) in {"EvidenceLevel.posthoc_exploratory", "posthoc_exploratory", "EvidenceLevel.exploratory", "exploratory"}

