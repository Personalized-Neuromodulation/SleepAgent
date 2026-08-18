from __future__ import annotations

import pytest

from sleep_ai_scientist.hypothesis.validation_spec import compile_grounding_validation_spec


def test_compile_grounding_validation_spec_locks_ranked_hypothesis() -> None:
    hypothesis = {
        "hypothesis_id": "hyp_001",
        "hypothesis": "Insomnia alters thalamo-cortical FC.",
        "source": "grounding",
        "evidence_ids": ["ev_001", "ev_002"],
        "candidate_fc": ["thalamus_DMN_FC", "DMN_salience_FC"],
        "expected_direction": {
            "thalamus_DMN_FC": "nonhealthy_greater",
            "DMN_salience_FC": "nonhealthy_lower",
        },
        "clinical_anchors": ["ISI", "PSQI"],
    }

    spec = compile_grounding_validation_spec(hypothesis, selected_rank=1)

    assert spec == {
        "source": "grounding",
        "locked": True,
        "selected_rank": 1,
        "hypothesis_id": "hyp_001",
        "hypothesis": "Insomnia alters thalamo-cortical FC.",
        "evidence_ids": ["ev_001", "ev_002"],
        "candidate_fc": ["thalamus_DMN_FC", "DMN_salience_FC"],
        "expected_direction": {
            "thalamus_DMN_FC": "nonhealthy_greater",
            "DMN_salience_FC": "nonhealthy_lower",
        },
        "clinical_anchors": ["ISI", "PSQI"],
        "validation_policy": {
            "local_data_role": "confirmatory_validation_only",
            "healthy_label_rule": "subject starts with sub-YZHC",
            "feature_selection": "candidate_fc must be prespecified by grounding before local outcome testing",
        },
    }


@pytest.mark.parametrize(
    "hypothesis, message",
    [
        (
            {
                "hypothesis_id": "hyp_local",
                "source": "local_data",
                "evidence_ids": ["ev_001"],
                "candidate_fc": ["thalamus_DMN_FC"],
            },
            "source='grounding'",
        ),
        (
            {
                "hypothesis_id": "hyp_no_fc",
                "source": "grounding",
                "evidence_ids": ["ev_001"],
                "candidate_fc": [],
            },
            "candidate_fc",
        ),
        (
            {
                "hypothesis_id": "hyp_no_evidence",
                "source": "grounding",
                "evidence_ids": [],
                "candidate_fc": ["thalamus_DMN_FC"],
            },
            "evidence_ids",
        ),
    ],
)
def test_compile_grounding_validation_spec_rejects_unlocked_inputs(
    hypothesis: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        compile_grounding_validation_spec(hypothesis)
