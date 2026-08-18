from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from sleep_ai_scientist.experiment.grounding_validation import run_grounding_locked_validation


def test_grounding_validation_sets_writable_plot_cache_dirs() -> None:
    assert os.environ["MPLCONFIGDIR"].startswith("/tmp/")
    assert os.environ["NUMBA_CACHE_DIR"].startswith("/tmp/")


def test_grounding_locked_validation_uses_prespecified_fc_and_subject_labels(tmp_path: Path) -> None:
    master = tmp_path / "master.csv"
    pd.DataFrame(
        [
            {
                "subject_id": "sub-YZHC001_ses-mri0_task-sleep0",
                "subject": "sub-YZHC001",
                "roi_fc_status": "computed",
                "has_fMRI": True,
                "thalamus_DMN_FC": 0.1,
                "DMN_salience_FC": 0.2,
                "ISI": 2,
                "leakage_FC": 99.0,
                "mean_FD": 0.10,
            },
            {
                "subject_id": "sub-YZHC001_ses-mri1_task-sleep1",
                "subject": "sub-YZHC001",
                "roi_fc_status": "computed",
                "has_fMRI": True,
                "thalamus_DMN_FC": 0.3,
                "DMN_salience_FC": 0.4,
                "ISI": 2,
                "leakage_FC": 101.0,
                "mean_FD": 0.20,
            },
            {
                "subject_id": "sub-ISM001_ses-mri0_task-sleep0",
                "subject": "sub-ISM001",
                "roi_fc_status": "computed",
                "has_fMRI": True,
                "thalamus_DMN_FC": 1.1,
                "DMN_salience_FC": 1.2,
                "ISI": 18,
                "leakage_FC": -99.0,
                "mean_FD": 0.30,
            },
            {
                "subject_id": "sub-ISM002_ses-mri0_task-sleep0",
                "subject": "sub-ISM002",
                "roi_fc_status": "computed",
                "has_fMRI": True,
                "thalamus_DMN_FC": 1.4,
                "DMN_salience_FC": 1.5,
                "ISI": 22,
                "leakage_FC": -101.0,
                "mean_FD": 0.40,
            },
        ]
    ).to_csv(master, index=False)
    spec = tmp_path / "hypothesis_from_grounding.json"
    spec.write_text(
        json.dumps(
            {
                "hypothesis_id": "grounding_fc_001",
                "hypothesis": "Grounding predicts thalamo-cortical FC changes.",
                "candidate_fc": ["thalamus_DMN_FC", "DMN_salience_FC"],
                "expected_direction": {
                    "thalamus_DMN_FC": "nonhealthy_greater",
                    "DMN_salience_FC": "nonhealthy_greater",
                },
                "clinical_anchors": ["ISI", "PSQI"],
                "source": "grounding",
            }
        ),
        encoding="utf-8",
    )

    result = run_grounding_locked_validation(master, spec, output_dir=tmp_path / "out", make_plots=False)

    subject_table = pd.read_csv(result["subject_table"]).sort_values("sample_id").reset_index(drop=True)
    assert list(subject_table["sample_id"]) == [
        "sub-ISM001_ses-mri0_task-sleep0",
        "sub-ISM002_ses-mri0_task-sleep0",
        "sub-YZHC001_ses-mri0_task-sleep0",
        "sub-YZHC001_ses-mri1_task-sleep1",
    ]
    assert subject_table.loc[subject_table["sample_id"] == "sub-YZHC001_ses-mri0_task-sleep0", "healthy_label"].item() == 1
    assert subject_table.loc[subject_table["sample_id"] == "sub-ISM001_ses-mri0_task-sleep0", "healthy_label"].item() == 0
    assert subject_table.loc[subject_table["sample_id"] == "sub-YZHC001_ses-mri0_task-sleep0", "thalamus_DMN_FC"].item() == 0.1
    assert subject_table.loc[subject_table["sample_id"] == "sub-YZHC001_ses-mri1_task-sleep1", "thalamus_DMN_FC"].item() == 0.3
    assert subject_table.loc[subject_table["sample_id"] == "sub-YZHC001_ses-mri1_task-sleep1", "ISI"].item() == 2
    assert "leakage_FC" not in subject_table.columns
    assert result["metadata"]["n_subjects"] == 3
    assert result["metadata"]["n_samples"] == 4
    assert result["metadata"]["n_healthy"] == 2
    assert result["metadata"]["n_nonhealthy"] == 2
    assert result["metadata"]["candidate_fc"] == ["thalamus_DMN_FC", "DMN_salience_FC"]
    assert result["metadata"]["source"] == "grounding"
    assert Path(result["feature_stats"]).exists()
    assert result["statistical_model"]["task"] == "locked_candidate_fc_group_contrast"
    assert "classification" not in result
    assert result["hypothesis_support"]["hypothesis_id"] == "grounding_fc_001"
    assert result["hypothesis_support"]["feature_support"][0]["feature"] == "thalamus_DMN_FC"
    assert Path(result["hypothesis_support_path"]).exists()


def test_grounding_locked_validation_reports_connectome_outputs(tmp_path: Path) -> None:
    pytest.importorskip("nilearn")
    pytest.importorskip("plotly")
    master = tmp_path / "master.csv"
    pd.DataFrame(
        [
            {"subject": "sub-YZHC001", "has_fMRI": True, "thalamus_DMN_FC": 0.1, "DMN_salience_FC": 0.2},
            {"subject": "sub-YZHC002", "has_fMRI": True, "thalamus_DMN_FC": 0.2, "DMN_salience_FC": 0.3},
            {"subject": "sub-ISM001", "has_fMRI": True, "thalamus_DMN_FC": 1.1, "DMN_salience_FC": 1.2},
            {"subject": "sub-ISM002", "has_fMRI": True, "thalamus_DMN_FC": 1.2, "DMN_salience_FC": 1.3},
        ]
    ).to_csv(master, index=False)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "source": "grounding",
                "hypothesis_id": "grounding_fc_figures",
                "candidate_fc": ["thalamus_DMN_FC", "DMN_salience_FC"],
                "expected_direction": {"thalamus_DMN_FC": "nonhealthy_greater"},
            }
        ),
        encoding="utf-8",
    )

    result = run_grounding_locked_validation(master, spec, output_dir=tmp_path / "out", make_plots=True)

    nilearn = [item for item in result["connection_visualizations"] if item["renderer"] == "nilearn_connectome"]
    three_d = [item for item in result["connection_visualizations"] if item["renderer"] == "nilearn_connectome_3d"]
    assert {item["kind"] for item in nilearn} == {
        "mean_difference_connectome",
        "significant_connectome",
    }
    assert {item["kind"] for item in three_d} == {
        "mean_difference_connectome_3d",
        "significant_connectome_3d",
    }
    assert all(Path(item["path"]).exists() for item in result["connection_visualizations"])
    assert all(Path(item["path"]).suffix in {".png", ".html"} for item in result["connection_visualizations"])
    html = (tmp_path / "out" / "figures" / "mean_difference_connectome_3d.html").read_text(encoding="utf-8")
    assert html.lower().startswith("<!doctype html>")
    assert "jQuery v3.6.0" in html
    assert "connectomeInfo" in html
    assert "marker_labels" in html
    assert "<iframe" not in html[:1000]
    assert "thalamus" in html
    assert "DMN" in html
    assert not (tmp_path / "out" / "figures" / "mean_difference_connections.png").exists()
    assert not (tmp_path / "out" / "figures" / "significant_connections.png").exists()
    assert not (tmp_path / "out" / "figures" / "classification_weight_connections.png").exists()
    assert not (tmp_path / "out" / "figures" / "classification_weight_connectome.png").exists()
    assert not (tmp_path / "out" / "figures" / "classification_weight_connectome_3d.html").exists()


def test_grounding_locked_validation_uses_atlas_derived_node_coordinates(tmp_path: Path) -> None:
    pytest.importorskip("nilearn")
    master = tmp_path / "master.csv"
    rows = []
    for subject, healthy, thalamus_x, dmn_x, fc in [
        ("sub-YZHC001", True, 11.0, 21.0, 0.1),
        ("sub-YZHC002", True, 13.0, 23.0, 0.2),
        ("sub-ISM001", False, 15.0, 25.0, 1.1),
        ("sub-ISM002", False, 17.0, 27.0, 1.2),
    ]:
        rows.append(
            {
                "subject": subject,
                "has_fMRI": True,
                "roi_fc_status": "computed",
                "thalamus_DMN_FC": fc,
                "thalamus_coord_x": thalamus_x,
                "thalamus_coord_y": -18.0,
                "thalamus_coord_z": 8.0,
                "DMN_coord_x": dmn_x,
                "DMN_coord_y": -52.0,
                "DMN_coord_z": 28.0,
                "roi_coord_source": "atlas:test_aparcaseg",
                "roi_coord_space": "atlas_image_world",
            }
        )
    pd.DataFrame(rows).to_csv(master, index=False)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps({"source": "grounding", "hypothesis_id": "grounding_fc_coords", "candidate_fc": ["thalamus_DMN_FC"]}),
        encoding="utf-8",
    )

    result = run_grounding_locked_validation(master, spec, output_dir=tmp_path / "out", make_plots=True)

    coords = pd.read_csv(result["node_coordinates"]).set_index("network")
    assert coords.loc["thalamus", "x"] == 14.0
    assert coords.loc["DMN", "x"] == 24.0
    assert coords.loc["thalamus", "coord_source"] == "atlas:test_aparcaseg"
    assert coords.loc["DMN", "coord_space"] == "atlas_image_world"
    html = (tmp_path / "out" / "figures" / "mean_difference_connectome_3d.html").read_text(encoding="utf-8")
    assert "坐标来源：</strong>atlas:test_aparcaseg" in html
    assert "坐标空间：</strong>atlas_image_world" in html
    assert "schematic fallback" not in html


def test_grounding_3d_connectome_explanation_separates_visible_edges_from_self_connections(tmp_path: Path) -> None:
    pytest.importorskip("nilearn")
    master = tmp_path / "master.csv"
    pd.DataFrame(
        [
            {"subject": "sub-YZHC001", "has_fMRI": True, "thalamus_DMN_FC": 0.1, "DMN_FC": 0.2},
            {"subject": "sub-YZHC002", "has_fMRI": True, "thalamus_DMN_FC": 0.1, "DMN_FC": 0.3},
            {"subject": "sub-ISM001", "has_fMRI": True, "thalamus_DMN_FC": 0.5, "DMN_FC": 0.8},
            {"subject": "sub-ISM002", "has_fMRI": True, "thalamus_DMN_FC": 0.7, "DMN_FC": 0.9},
        ]
    ).to_csv(master, index=False)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "source": "grounding",
                "hypothesis_id": "grounding_fc_self_edges",
                "candidate_fc": ["thalamus_DMN_FC", "DMN_FC"],
            }
        ),
        encoding="utf-8",
    )

    run_grounding_locked_validation(master, spec, output_dir=tmp_path / "out", make_plots=True)

    html = (tmp_path / "out" / "figures" / "mean_difference_connectome_3d.html").read_text(encoding="utf-8")
    assert "候选 FC 总数：</strong>2" in html
    assert "图中可见跨节点连接：</strong>1" in html
    assert "网络内部/自连接：</strong>1" in html


def test_grounding_locked_validation_reports_nilearn_connectome_outputs(tmp_path: Path) -> None:
    pytest.importorskip("nilearn")
    master = tmp_path / "master.csv"
    pd.DataFrame(
        [
            {"subject": "sub-YZHC001", "has_fMRI": True, "thalamus_DMN_FC": 0.1, "DMN_salience_FC": 0.2},
            {"subject": "sub-YZHC002", "has_fMRI": True, "thalamus_DMN_FC": 0.2, "DMN_salience_FC": 0.3},
            {"subject": "sub-ISM001", "has_fMRI": True, "thalamus_DMN_FC": 1.1, "DMN_salience_FC": 1.2},
            {"subject": "sub-ISM002", "has_fMRI": True, "thalamus_DMN_FC": 1.2, "DMN_salience_FC": 1.3},
        ]
    ).to_csv(master, index=False)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "source": "grounding",
                "hypothesis_id": "grounding_fc_connectome",
                "candidate_fc": ["thalamus_DMN_FC", "DMN_salience_FC"],
                "expected_direction": {"thalamus_DMN_FC": "nonhealthy_greater"},
            }
        ),
        encoding="utf-8",
    )

    result = run_grounding_locked_validation(master, spec, output_dir=tmp_path / "out", make_plots=True)

    connectomes = [item for item in result["connection_visualizations"] if item["renderer"] == "nilearn_connectome"]
    assert {item["kind"] for item in connectomes} >= {
        "mean_difference_connectome",
        "significant_connectome",
    }
    assert all(Path(item["path"]).exists() for item in connectomes)


def test_grounding_group_contrast_models_nonhealthy_symptom_links_and_interactions(tmp_path: Path) -> None:
    master = tmp_path / "master_with_symptoms.csv"
    pd.DataFrame(
        [
            {"subject": "sub-YZHC001", "has_fMRI": True, "thalamus_DMN_FC": 0.1, "DMN_salience_FC": 0.3, "ISI": 2, "PSQI": 3},
            {"subject": "sub-YZHC002", "has_fMRI": True, "thalamus_DMN_FC": 0.2, "DMN_salience_FC": 0.2, "ISI": 3, "PSQI": 4},
            {"subject": "sub-YZHC003", "has_fMRI": True, "thalamus_DMN_FC": 0.3, "DMN_salience_FC": 0.1, "ISI": 4, "PSQI": 5},
            {"subject": "sub-ISM001", "has_fMRI": True, "thalamus_DMN_FC": 0.4, "DMN_salience_FC": 0.1, "ISI": 8, "PSQI": 7},
            {"subject": "sub-ISM002", "has_fMRI": True, "thalamus_DMN_FC": 0.6, "DMN_salience_FC": 0.2, "ISI": 12, "PSQI": 10},
            {"subject": "sub-ISM003", "has_fMRI": True, "thalamus_DMN_FC": 0.8, "DMN_salience_FC": 0.3, "ISI": 16, "PSQI": 13},
        ]
    ).to_csv(master, index=False)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "source": "grounding",
                "hypothesis_id": "grounding_fc_group_mechanism",
                "candidate_fc": ["thalamus_DMN_FC", "DMN_salience_FC"],
                "clinical_anchors": ["ISI", "PSQI"],
            }
        ),
        encoding="utf-8",
    )

    result = run_grounding_locked_validation(master, spec, output_dir=tmp_path / "out", make_plots=False)

    symptom_stats = pd.read_csv(result["group_symptom_stats"])
    assert set(symptom_stats["clinical_anchor"]) == {"ISI", "PSQI"}
    assert set(symptom_stats["feature"]) == {"thalamus_DMN_FC", "DMN_salience_FC"}
    assert "nonhealthy_spearman_r" in symptom_stats.columns
    assert "healthy_spearman_r" in symptom_stats.columns
    assert "group_fc_interaction_p" in symptom_stats.columns
    thalamus_isi = symptom_stats[
        (symptom_stats["feature"] == "thalamus_DMN_FC") & (symptom_stats["clinical_anchor"] == "ISI")
    ].iloc[0]
    assert thalamus_isi["nonhealthy_spearman_r"] > 0
    assert result["statistical_model"]["task"] == "locked_candidate_fc_group_contrast"
    assert result["statistical_model"]["symptom_association"] == str(result["group_symptom_stats"])


def test_grounding_locked_validation_writes_significant_connectome_when_no_fdr_edges(tmp_path: Path) -> None:
    pytest.importorskip("nilearn")
    master = tmp_path / "master.csv"
    pd.DataFrame(
        [
            {"subject": "sub-YZHC001", "has_fMRI": True, "thalamus_DMN_FC": 0.1, "DMN_salience_FC": 0.2},
            {"subject": "sub-YZHC002", "has_fMRI": True, "thalamus_DMN_FC": 0.1, "DMN_salience_FC": 0.2},
            {"subject": "sub-ISM001", "has_fMRI": True, "thalamus_DMN_FC": 0.1, "DMN_salience_FC": 0.2},
            {"subject": "sub-ISM002", "has_fMRI": True, "thalamus_DMN_FC": 0.1, "DMN_salience_FC": 0.2},
        ]
    ).to_csv(master, index=False)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "source": "grounding",
                "hypothesis_id": "grounding_fc_no_fdr_edges",
                "candidate_fc": ["thalamus_DMN_FC", "DMN_salience_FC"],
            }
        ),
        encoding="utf-8",
    )

    result = run_grounding_locked_validation(master, spec, output_dir=tmp_path / "out", make_plots=True)

    significant = [
        item
        for item in result["connection_visualizations"]
        if item["kind"] == "significant_connectome" and item["renderer"] == "nilearn_connectome"
    ]
    assert len(significant) == 1
    assert Path(significant[0]["path"]).exists()


def test_grounding_locked_validation_rejects_non_grounding_specs(tmp_path: Path) -> None:
    master = tmp_path / "master.csv"
    pd.DataFrame(
        [
            {"subject": "sub-YZHC001", "roi_fc_status": "computed", "has_fMRI": True, "thalamus_DMN_FC": 0.1},
            {"subject": "sub-ISM001", "roi_fc_status": "computed", "has_fMRI": True, "thalamus_DMN_FC": 1.1},
        ]
    ).to_csv(master, index=False)
    spec = tmp_path / "bad_spec.json"
    spec.write_text(json.dumps({"source": "local_data", "candidate_fc": ["thalamus_DMN_FC"]}), encoding="utf-8")

    try:
        run_grounding_locked_validation(master, spec, output_dir=tmp_path / "out", make_plots=False)
    except ValueError as exc:
        assert "grounding" in str(exc)
    else:
        raise AssertionError("Expected non-grounding specs to be rejected")


def test_grounding_locked_validation_retains_available_clinical_anchors(tmp_path: Path) -> None:
    master = tmp_path / "master_with_scales.csv"
    pd.DataFrame(
        [
            {
                "subject": "sub-YZHC001",
                "roi_fc_status": "computed",
                "has_fMRI": True,
                "thalamus_DMN_FC": 0.1,
                "ISI": 2,
                "PSQI": 3,
                "BAI": 1,
                "BDI": 0,
                "sleepiness": 4,
                "leakage_FC": 99,
            },
            {
                "subject": "sub-ISM001",
                "roi_fc_status": "computed",
                "has_fMRI": True,
                "thalamus_DMN_FC": 1.1,
                "ISI": 18,
                "PSQI": 12,
                "BAI": 10,
                "BDI": 9,
                "sleepiness": 8,
                "leakage_FC": -99,
            },
        ]
    ).to_csv(master, index=False)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "source": "grounding",
                "hypothesis_id": "grounding_fc_scales",
                "candidate_fc": ["thalamus_DMN_FC"],
                "clinical_anchors": ["ISI", "PSQI", "BAI", "BDI", "sleepiness"],
            }
        ),
        encoding="utf-8",
    )

    result = run_grounding_locked_validation(master, spec, output_dir=tmp_path / "out", make_plots=False)

    subject_table = pd.read_csv(result["subject_table"])
    for column in ["ISI", "PSQI", "BAI", "BDI", "sleepiness"]:
        assert column in subject_table.columns
    assert "leakage_FC" not in subject_table.columns
    assert subject_table.loc[subject_table["subject"] == "sub-ISM001", "ISI"].item() == 18
    assert result["metadata"]["clinical_anchors"] == ["ISI", "PSQI", "BAI", "BDI", "sleepiness"]


def test_grounding_locked_validation_resolves_fmri_prefixed_merge_columns(tmp_path: Path) -> None:
    master = tmp_path / "merged.csv"
    pd.DataFrame(
        [
            {
                "subject": "sub-YZHC001",
                "fmri_roi_fc_status": "computed",
                "fmri_has_fMRI": 1.0,
                "fmri_thalamus_DMN_FC": 0.1,
                "scales_ISI": 2,
            },
            {
                "subject": "sub-ISM001",
                "fmri_roi_fc_status": "computed",
                "fmri_has_fMRI": 1.0,
                "fmri_thalamus_DMN_FC": 1.1,
                "scales_ISI": 18,
            },
        ]
    ).to_csv(master, index=False)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "source": "grounding",
                "hypothesis_id": "grounding_fc_prefixed",
                "candidate_fc": ["thalamus_DMN_FC"],
                "clinical_anchors": ["ISI"],
            }
        ),
        encoding="utf-8",
    )

    result = run_grounding_locked_validation(master, spec, output_dir=tmp_path / "out", make_plots=False)

    subject_table = pd.read_csv(result["subject_table"])
    assert "thalamus_DMN_FC" in subject_table.columns
    assert "fmri_thalamus_DMN_FC" not in subject_table.columns
    assert subject_table.loc[subject_table["subject"] == "sub-ISM001", "thalamus_DMN_FC"].item() == 1.1
    assert subject_table.loc[subject_table["subject"] == "sub-ISM001", "ISI"].item() == 18
