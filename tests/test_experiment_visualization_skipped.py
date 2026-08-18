from __future__ import annotations

from pathlib import Path

import pandas as pd

from sleep_ai_scientist.experiment.agents.analysis_templates import run_primary_tests
from sleep_ai_scientist.experiment.visualization import render_experiment_visualizations
from sleep_ai_scientist.schemas.experiment import ExperimentPlan, ExperimentResultBundle, ExperimentVariable, ExperimentVariableRole, StatsAgentResult


def test_render_experiment_visualizations_reports_skipped_plans(tmp_path: Path) -> None:
    manifest = render_experiment_visualizations(
        [],
        tmp_path / "visuals",
        skipped_plans=[
            {
                "plan_id": "plan_dup",
                "hypothesis_id": "hyp_dup",
                "reason": "duplicate_experiment_signature",
                "stage": "post_mapping_pre_statistics",
            }
        ],
    )

    figures = [Path(path).name for path in manifest["figures"]]
    assert figures == ["skipped_plans_diagnostic.png"]
    assert manifest["dashboard"]["skipped_plans"][0]["reason"] == "duplicate_experiment_signature"
    assert manifest["figure_records"][0]["kind"] == "skipped_plans"
    assert Path(manifest["figures"][0]).exists()


def test_render_experiment_visualizations_adds_group_specific_scatter(tmp_path: Path) -> None:
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
    plan = ExperimentPlan(
        plan_id="plan_group",
        hypothesis_id="hyp_group",
        hypothesis_title="h",
        scientific_question="q",
        predictors=["thalamus_DMN_FC"],
        outcomes=["ISI"],
        variables=[
            ExperimentVariable(
                name="thalamus_DMN_FC",
                role=ExperimentVariableRole.predictor,
                modality="fMRI",
                source_file=str(features),
                source_column="thalamus_DMN_FC",
            ),
            ExperimentVariable(
                name="ISI",
                role=ExperimentVariableRole.outcome,
                modality="scales",
                source_file=str(features),
                source_column="ISI",
            ),
        ],
        primary_tests=[{"test_id": "test_group", "predictor": "thalamus_DMN_FC", "outcome": "ISI"}],
    )
    tests = run_primary_tests(plan)
    bundle = ExperimentResultBundle(
        plan=plan,
        stats_result=StatsAgentResult(plan_id=plan.plan_id, hypothesis_id=plan.hypothesis_id, tests=tests),
    )

    manifest = render_experiment_visualizations([bundle], tmp_path / "visuals")

    figures = [Path(path).name for path in manifest["figures"]]
    assert "group_specific_scatter_test_group.png" in figures
