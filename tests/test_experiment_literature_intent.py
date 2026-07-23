from pathlib import Path

from sleep_ai_scientist.common.io import read_yaml, write_yaml
from sleep_ai_scientist.literature.experiment_intent import (
    append_queries_to_config,
    build_literature_expansion_plan,
)


def _write_query_config(path: Path) -> None:
    write_yaml(
        path,
        {
            "query_file": {"version": "test"},
            "query_sets": {
                "library": {
                    "query_set": {"version": "test"},
                    "settings": {"providers": ["pubmed"], "max_results_per_query": 5},
                    "queries": {
                        "human_sleep_neuroimaging": [
                            "sleep fMRI global signal regression fALFF",
                            "sleep thalamus connectivity fMRI",
                        ]
                    },
                }
            },
        },
    )


def _experiment_summary() -> dict:
    return {
        "plans": 1,
        "results_payload": [
            {
                "plan": {
                    "hypothesis_id": "hypothesis_abc",
                    "plan_id": "plan_123",
                    "hypothesis_title": "Thalamic spindle modulation via FA and cortical slow oscillations",
                    "hypothesis_content": "FA, cortical slow oscillations, and thalamocortical coupling modulate spindle density.",
                    "predictors": ["thalamus_DMN_FC", "timefreq_fALFF_0.01_0.08_over_0.01_0.25"],
                    "outcomes": ["salience_FC", "frontoparietal_FC"],
                    "metadata": {
                        "testability_precheck": {
                            "reason": "Only fMRI features are available; cannot directly test missing morphology, DTI, EEG, or scale outcomes.",
                            "excluded_modalities": ["DTI", "EEG", "PSG"],
                        },
                        "variable_mapping_review": {
                            "missing_variables": [
                                "thalamus_roi_voxels",
                                "DMN_roi_voxels",
                                "salience_roi_voxels",
                                "frontoparietal_roi_voxels",
                            ]
                        },
                    },
                },
                "stats_result": {
                    "tests": [
                        {
                            "predictor": "thalamus_DMN_FC",
                            "outcome": "salience_FC",
                            "p_value": 0.24,
                            "passed": False,
                        },
                        {
                            "predictor": "thalamus_DMN_FC",
                            "outcome": "frontoparietal_FC",
                            "p_value": 0.01,
                            "passed": True,
                        },
                    ]
                },
                "negative_control_results": [
                    {
                        "predictor": "timefreq_fALFF_0.01_0.08_over_0.01_0.25",
                        "outcome": "global_signal_psd_power_mean",
                        "passed": False,
                    }
                ],
                "critic_findings": [
                    {
                        "category": "missing_data",
                        "message": "Missing ROI voxel count variables may affect model accuracy.",
                    }
                ],
                "evidence_update": {
                    "review_status": "partially_supported",
                    "support_score": 0.75,
                    "result_review": {
                        "confounds": ["mean FD"],
                        "alternative_explanations": [
                            "Non-linear relationships between FC and outcomes could influence results."
                        ],
                    },
                },
            }
        ],
        "feedback_payload": [
            {
                "hypothesis_id": "hypothesis_abc",
                "plan_id": "plan_123",
                "computed_reward": 0.75,
                "validated": True,
                "support": "partially_supported",
            }
        ],
    }


def test_build_literature_expansion_plan_generates_validated_deduped_queries(tmp_path):
    query_config = tmp_path / "literature_queries.yaml"
    _write_query_config(query_config)

    plan = build_literature_expansion_plan(
        _experiment_summary(),
        "iteration_002",
        query_config,
        max_queries=8,
    )

    accepted_queries = [item["query"] for item in plan["accepted_queries"]]
    assert plan["accepted_query_count"] > 0
    assert "sleep fMRI global signal regression fALFF" not in accepted_queries
    assert "thalamus default mode network salience network functional connectivity sleep fMRI" in accepted_queries
    assert "fALFF global signal confound resting state fMRI sleep" in accepted_queries
    assert any(item["intent_type"] == "fill_modality_gap" for item in plan["accepted_queries"])
    assert plan["rejected_duplicate_count"] >= 1
    assert plan["signals"]["failed_tests"] == 1
    assert plan["signals"]["negative_control_failures"] == 1
    assert plan["signals"]["missing_variables"] == 4
    assert plan["accepted_queries"][0]["source_iteration"] == "iteration_002"
    assert plan["accepted_queries"][0]["source_hypothesis_id"] == "hypothesis_abc"


def test_append_queries_to_config_writes_experiment_feedback_group(tmp_path):
    query_config = tmp_path / "literature_queries.yaml"
    _write_query_config(query_config)
    accepted = [
        {
            "query": "thalamus default mode network salience network functional connectivity sleep fMRI",
            "intent_type": "resolve_failed_test",
            "priority": 0.84,
        }
    ]

    summary = append_queries_to_config(query_config, accepted)

    payload = read_yaml(query_config)
    queries = payload["query_sets"]["library"]["queries"]["experiment_feedback_expansion"]
    assert summary == {
        "appended": 1,
        "group": "experiment_feedback_expansion",
        "query_config": str(query_config),
    }
    assert queries == ["thalamus default mode network salience network functional connectivity sleep fMRI"]
