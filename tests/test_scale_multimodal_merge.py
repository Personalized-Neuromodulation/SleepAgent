from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sleep_ai_scientist.feature_extraction.extractors.multimodal_merger import MultimodalMerger
from sleep_ai_scientist.feature_extraction.schemas import FeatureTable


def test_multimodal_merger_replicates_baseline_scales_to_each_fmri_session(tmp_path: Path) -> None:
    fmri_path = tmp_path / "fmri.csv"
    pd.DataFrame(
        [
            {"subject_id": "sub-ISM035_ses-mri0", "thalamus_DMN_FC": 0.2},
            {"subject_id": "sub-ISM035_ses-mri1", "thalamus_DMN_FC": 0.4},
        ]
    ).to_csv(fmri_path, index=False)
    scale_path = tmp_path / "scale_features.csv"
    pd.DataFrame(
        [
            {
                "subject_id": "sub-ISM035",
                "subject": "sub-ISM035",
                "ISI": 18,
                "PSQI": 13,
                "BAI": 23,
                "BDI": 22,
                "sleepiness": 1,
                "baseline_source_visit": "0w",
                "baseline_is_substituted": False,
            }
        ]
    ).to_csv(scale_path, index=False)
    tables = [
        FeatureTable(modality="fmri", path=str(fmri_path)),
        FeatureTable(modality="scales", path=str(scale_path)),
    ]

    merged_path = MultimodalMerger().run(tables, tmp_path / "merged.csv")

    merged = pd.read_csv(merged_path).set_index("subject_id")
    assert len(merged) == 2
    assert merged.loc["sub-ISM035_ses-mri0", "subject"] == "sub-ISM035"
    assert merged.loc["sub-ISM035_ses-mri1", "subject"] == "sub-ISM035"
    assert merged.loc["sub-ISM035_ses-mri0", "fmri_thalamus_DMN_FC"] == pytest.approx(0.2)
    assert merged.loc["sub-ISM035_ses-mri1", "fmri_thalamus_DMN_FC"] == pytest.approx(0.4)
    assert merged.loc["sub-ISM035_ses-mri0", "scales_ISI"] == 18
    assert merged.loc["sub-ISM035_ses-mri1", "scales_ISI"] == 18
    assert merged.loc["sub-ISM035_ses-mri0", "scales_baseline_source_visit"] == "0w"
    assert bool(merged.loc["sub-ISM035_ses-mri0", "scales_baseline_is_substituted"]) is False
