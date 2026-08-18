from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sleep_ai_scientist.experiment.agents.analysis_templates import load_analysis_table, run_primary_tests
from sleep_ai_scientist.experiment.experiment_pipeline import _group_specific_model_records
from sleep_ai_scientist.schemas.experiment import ExperimentPlan, ExperimentVariable, ExperimentVariableRole
from sleep_ai_scientist.schemas.experiment import ExperimentResultBundle, StatsAgentResult


def test_load_analysis_table_adds_healthy_label_from_subject_id(tmp_path: Path) -> None:
    features = tmp_path / "features.csv"
    pd.DataFrame(
        [
            {"subject_id": "sub-YZHC001_ses-mri0", "thalamus_DMN_FC": 0.1},
            {"subject_id": "sub-ISM001_ses-mri0", "thalamus_DMN_FC": 0.9},
        ]
    ).to_csv(features, index=False)
    plan = _plan(features)

    table = load_analysis_table(plan, {"thalamus_DMN_FC"})

    assert table.loc[table["subject_id"] == "sub-YZHC001_ses-mri0", "subject"].item() == "sub-YZHC001"
    assert table.loc[table["subject_id"] == "sub-YZHC001_ses-mri0", "healthy_label"].item() == 1
    assert table.loc[table["subject_id"] == "sub-ISM001_ses-mri0", "healthy_label"].item() == 0


def test_primary_tests_include_health_group_and_scale_context(tmp_path: Path) -> None:
    features = tmp_path / "features.csv"
    pd.DataFrame(
        [
            {"subject_id": "sub-YZHC001", "thalamus_DMN_FC": 0.1, "ISI": 2},
            {"subject_id": "sub-YZHC002", "thalamus_DMN_FC": 0.2, "ISI": 3},
            {"subject_id": "sub-ISM001", "thalamus_DMN_FC": 0.8, "ISI": 16},
            {"subject_id": "sub-ISM002", "thalamus_DMN_FC": 0.9, "ISI": 18},
        ]
    ).to_csv(features, index=False)
    plan = _plan(features)

    result = run_primary_tests(plan, primary_template="spearman_correlation")[0]

    context = result.metadata["clinical_group_context"]
    assert context["task"] == "healthy_vs_nonhealthy_context"
    assert context["n_healthy"] == 2
    assert context["n_nonhealthy"] == 2
    assert context["predictor_group_difference"]["nonhealthy_minus_healthy"] == pytest.approx(0.7)
    assert context["outcome_group_difference"]["nonhealthy_minus_healthy"] == pytest.approx(14.5)
    assert context["outcome_group_difference"]["is_scale_anchor"] is True
    assert context["predictor_group_difference"]["fdr_q"] is not None
    assert context["outcome_group_difference"]["fdr_q"] is not None
    assert context["clinical_interpretation"] == "fc_and_scale_both_different_between_groups"


def test_primary_tests_include_within_group_predictor_outcome_associations(tmp_path: Path) -> None:
    features = tmp_path / "features.csv"
    pd.DataFrame(
        [
            {"subject_id": "sub-YZHC001", "thalamus_DMN_FC": 0.1, "ISI": 2},
            {"subject_id": "sub-YZHC002", "thalamus_DMN_FC": 0.2, "ISI": 3},
            {"subject_id": "sub-YZHC003", "thalamus_DMN_FC": 0.3, "ISI": 4},
            {"subject_id": "sub-ISM001", "thalamus_DMN_FC": 0.9, "ISI": 18},
            {"subject_id": "sub-ISM002", "thalamus_DMN_FC": 0.8, "ISI": 16},
            {"subject_id": "sub-ISM003", "thalamus_DMN_FC": 0.7, "ISI": 14},
        ]
    ).to_csv(features, index=False)
    plan = _plan(features)

    result = run_primary_tests(plan, primary_template="spearman_correlation")[0]

    associations = result.metadata["clinical_group_context"]["within_group_associations"]
    assert associations["method"] == "spearman_correlation"
    assert associations["healthy"]["n"] == 3
    assert associations["healthy"]["effect"] == pytest.approx(1.0)
    assert associations["healthy"]["direction"] == "positive"
    assert associations["nonhealthy"]["n"] == 3
    assert associations["nonhealthy"]["effect"] == pytest.approx(1.0)
    assert associations["nonhealthy"]["direction"] == "positive"
    assert associations["effect_difference_hint"] == pytest.approx(0.0)


def test_primary_tests_include_group_specific_models_and_interaction(tmp_path: Path) -> None:
    features = tmp_path / "features.csv"
    rows = []
    noise = [0.1, -0.1, 0.05, -0.05, 0.0, 0.03, -0.03, 0.02]
    for idx, x_value in enumerate(range(8)):
        rows.append({"subject_id": f"sub-YZHC{idx:03d}", "thalamus_DMN_FC": x_value, "ISI": 5 + 0.05 * x_value + noise[idx]})
        rows.append({"subject_id": f"sub-ISM{idx:03d}", "thalamus_DMN_FC": x_value, "ISI": 1 + 2.0 * x_value + noise[idx]})
    pd.DataFrame(rows).to_csv(features, index=False)
    plan = _plan(features)

    result = run_primary_tests(plan, primary_template="spearman_correlation")[0]

    models = result.metadata["clinical_group_context"]["group_specific_models"]
    assert models["healthy"]["status"] == "run"
    assert models["nonhealthy"]["status"] == "run"
    assert models["interaction"]["status"] == "run"
    assert models["healthy"]["slope"] == pytest.approx(0.05, abs=0.02)
    assert models["nonhealthy"]["slope"] == pytest.approx(2.0, abs=0.02)
    assert models["interaction"]["p_value"] < 0.001
    assert models["interaction"]["interpretation"] == "group_specific_slope_difference"


def test_group_specific_model_records_flatten_test_metadata(tmp_path: Path) -> None:
    features = tmp_path / "features.csv"
    pd.DataFrame(
        [
            {"subject_id": "sub-YZHC001", "thalamus_DMN_FC": 0.1, "ISI": 2},
            {"subject_id": "sub-YZHC002", "thalamus_DMN_FC": 0.2, "ISI": 3},
            {"subject_id": "sub-YZHC003", "thalamus_DMN_FC": 0.3, "ISI": 4},
            {"subject_id": "sub-ISM001", "thalamus_DMN_FC": 0.7, "ISI": 14},
            {"subject_id": "sub-ISM002", "thalamus_DMN_FC": 0.8, "ISI": 16},
            {"subject_id": "sub-ISM003", "thalamus_DMN_FC": 0.9, "ISI": 18},
        ]
    ).to_csv(features, index=False)
    plan = _plan(features)
    tests = run_primary_tests(plan, primary_template="spearman_correlation")
    bundle = ExperimentResultBundle(plan=plan, stats_result=StatsAgentResult(plan_id=plan.plan_id, hypothesis_id=plan.hypothesis_id, tests=tests))

    records = _group_specific_model_records([bundle])

    assert len(records) == 1
    assert records[0]["plan_id"] == "plan"
    assert records[0]["predictor"] == "thalamus_DMN_FC"
    assert records[0]["outcome"] == "ISI"
    assert records[0]["healthy_n"] == 3
    assert records[0]["nonhealthy_n"] == 3
    assert "interaction_p_value" in records[0]


def _plan(path: Path) -> ExperimentPlan:
    return ExperimentPlan(
        plan_id="plan",
        hypothesis_id="hyp",
        hypothesis_title="h",
        scientific_question="q",
        predictors=["thalamus_DMN_FC"],
        outcomes=["ISI"],
        variables=[
            ExperimentVariable(
                name="thalamus_DMN_FC",
                role=ExperimentVariableRole.predictor,
                modality="fMRI",
                source_file=str(path),
                source_column="thalamus_DMN_FC",
            ),
            ExperimentVariable(
                name="ISI",
                role=ExperimentVariableRole.outcome,
                modality="scales",
                source_file=str(path),
                source_column="ISI",
            ),
        ],
        primary_tests=[{"predictor": "thalamus_DMN_FC", "outcome": "ISI", "model": "spearman_correlation"}],
    )
