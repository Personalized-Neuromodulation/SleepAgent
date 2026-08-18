from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sleep_ai_scientist.experiment.agents.analysis_templates import load_analysis_table
from sleep_ai_scientist.schemas.experiment import ExperimentPlan, ExperimentVariable, ExperimentVariableRole


def test_load_analysis_table_replicates_baseline_scales_to_each_fmri_session(tmp_path: Path) -> None:
    fmri = tmp_path / "fmri.csv"
    pd.DataFrame(
        [
            {"subject_id": "sub-ISM035_ses-mri0", "thalamus_DMN_FC": 0.2},
            {"subject_id": "sub-ISM035_ses-mri1", "thalamus_DMN_FC": 0.4},
        ]
    ).to_csv(fmri, index=False)
    scales = tmp_path / "scale_features.csv"
    pd.DataFrame([{"subject_id": "sub-ISM035", "ISI": 18}]).to_csv(scales, index=False)
    plan = ExperimentPlan(
        plan_id="plan",
        hypothesis_id="hyp",
        hypothesis_title="h",
        scientific_question="q",
        variables=[
            ExperimentVariable(
                name="thalamus_DMN_FC",
                role=ExperimentVariableRole.predictor,
                modality="fMRI",
                source_file=str(fmri),
                source_column="thalamus_DMN_FC",
            ),
            ExperimentVariable(
                name="ISI",
                role=ExperimentVariableRole.outcome,
                modality="scales",
                source_file=str(scales),
                source_column="ISI",
            ),
        ],
    )

    table = load_analysis_table(plan, {"thalamus_DMN_FC", "ISI"})

    table = table.sort_values("subject_id").reset_index(drop=True)
    assert len(table) == 2
    assert table.loc[0, "subject_id"] == "sub-ISM035_ses-mri0"
    assert table.loc[1, "subject_id"] == "sub-ISM035_ses-mri1"
    assert table.loc[0, "subject"] == "sub-ISM035"
    assert table.loc[0, "thalamus_DMN_FC"] == pytest.approx(0.2)
    assert table.loc[1, "thalamus_DMN_FC"] == pytest.approx(0.4)
    assert table["ISI"].tolist() == [18, 18]
