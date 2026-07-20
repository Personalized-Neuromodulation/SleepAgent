from pathlib import Path

import pandas as pd

from sleep_ai_scientist.common.io import read_json, write_yaml
from sleep_ai_scientist.experiment.agents.llm import build_experiment_llm, experiment_llm_enabled
from sleep_ai_scientist.experiment.agents.analysis_templates import run_primary_tests
from sleep_ai_scientist.experiment.agents.planning import build_experiment_plan_from_hypothesis, load_data_profile, load_hypotheses
from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline
from sleep_ai_scientist.feature_extraction.feature_pipeline import run_feature_extraction
from sleep_ai_scientist.feature_extraction.profile_builder import TestabilityPrecheck
from sleep_ai_scientist.schemas.data_profile import DataProfile, FeatureProfile
from sleep_ai_scientist.schemas.experiment import ExperimentPlan, ExperimentVariable, ExperimentVariableRole


def test_experiment_agent_plan_is_not_empty_shell():
    hypotheses = sorted(
        load_hypotheses("outputs/hypotheses/hypothesis_pool.json"),
        key=lambda item: item.elo_rating,
        reverse=True,
    )
    profile = load_data_profile("outputs/profiles/analysis_ready_profile.yaml")
    plan = build_experiment_plan_from_hypothesis(hypotheses[0], profile)

    assert plan.hypothesis_id == hypotheses[0].hypothesis_id
    assert plan.predictors
    assert plan.outcomes
    assert plan.variables
    assert plan.primary_tests


def test_experiment_pipeline_runs_with_controlled_agents(tmp_path):
    config_path = tmp_path / "experiment_config.yaml"
    results_path = tmp_path / "experiments" / "experiment_results.json"
    feedback_path = tmp_path / "hypotheses" / "experimental_feedback.json"
    report_path = tmp_path / "reports" / "experiment_report.md"
    write_yaml(
        config_path,
        {
            "experiment": {
                "top_k_hypotheses": 1,
                "bootstrap_iterations": 5,
                "enable_ml": False,
                "verbose": False,
                "llm": {
                    "enabled": False,
                    "provider": "ollama",
                    "base_url": "http://localhost:11434",
                    "model": "deepseek-coder-v2:16b",
                },
            },
            "paths": {
                "hypothesis_pool": str(Path("outputs/hypotheses/hypothesis_pool.json").resolve()),
                "data_profile": str(Path("outputs/profiles/analysis_ready_profile.yaml").resolve()),
                "approved_variables": str(Path("outputs/grounding/approved_variables_from_grounding.yaml").resolve()),
                "variable_mapping": str(Path("outputs/grounding/evidence_to_variable_map.yaml").resolve()),
                "experiment_output_dir": str(tmp_path / "experiments"),
                "experiment_results": str(results_path),
                "experimental_feedback": str(feedback_path),
                "experiment_report": str(report_path),
            },
        },
    )

    summary = run_experiment_pipeline(config_path)
    assert summary["plans"] == 1
    assert results_path.exists()
    assert feedback_path.exists()
    assert report_path.exists()
    assert read_json(results_path)[0]["stats_result"]["tests"]
    assert read_json(feedback_path)[0]["metadata"]["review_status"] == "not_adjudicated"


def test_experiment_pipeline_runs_feature_extraction_layer(tmp_path):
    config_path = tmp_path / "experiment_config.yaml"
    feature_root = tmp_path / "features"
    results_path = tmp_path / "experiments" / "experiment_results.json"
    feedback_path = tmp_path / "hypotheses" / "experimental_feedback.json"
    report_path = tmp_path / "reports" / "experiment_report.md"
    write_yaml(
        config_path,
        {
            "experiment": {
                "top_k_hypotheses": 1,
                "bootstrap_iterations": 5,
                "enable_ml": False,
                "verbose": False,
                "llm": {"enabled": False, "provider": "ollama", "model": "deepseek-coder-v2:16b"},
            },
            "feature_extraction": {
                "enabled": True,
                "output_root": str(feature_root),
                "modalities": ["fmri", "eeg", "scales"],
                "fmri": {"features_csv": str(Path("data/fixtures/toy_fmri_features.csv").resolve())},
                "eeg": {"features_csv": str(Path("data/fixtures/toy_eeg_features.csv").resolve())},
                "scales": {"features_csv": str(Path("data/fixtures/toy_scale_features.csv").resolve())},
            },
            "paths": {
                "hypothesis_pool": str(Path("outputs/hypotheses/hypothesis_pool.json").resolve()),
                "data_profile": str(Path("outputs/profiles/analysis_ready_profile.yaml").resolve()),
                "approved_variables": str(Path("outputs/grounding/approved_variables_from_grounding.yaml").resolve()),
                "variable_mapping": str(Path("outputs/grounding/evidence_to_variable_map.yaml").resolve()),
                "experiment_output_dir": str(tmp_path / "experiments"),
                "experiment_results": str(results_path),
                "experimental_feedback": str(feedback_path),
                "experiment_report": str(report_path),
            },
        },
    )

    summary = run_experiment_pipeline(config_path)
    assert summary["plans"] == 1
    assert list((feature_root / "fmri").glob("*/fmri_features.csv"))
    assert list((feature_root / "eeg").glob("*/eeg_features.csv"))
    assert list((feature_root / "scales").glob("*/scale_features.csv"))
    assert list((feature_root / "profile").glob("*/analysis_ready_profile.yaml"))
    assert list((feature_root / "multimodal").glob("*/multimodal_features.csv"))
    assert read_json(results_path)[0]["stats_result"]["tests"]


def test_feature_extraction_auto_uses_only_configured_fmri(tmp_path):
    hypotheses = load_hypotheses("outputs/hypotheses/hypothesis_pool.json")
    profile = load_data_profile("outputs/profiles/analysis_ready_profile.yaml")
    plan = build_experiment_plan_from_hypothesis(hypotheses[0], profile)

    result = run_feature_extraction(
        {
            "output_root": str(tmp_path / "features"),
            "modalities": "auto",
            "fmri": {"features_csv": str(Path("data/fixtures/toy_fmri_features.csv").resolve())},
            "eeg": {"features_csv": ""},
            "scales": {"features_csv": ""},
        },
        plan,
    )

    assert [table.modality for table in result.tables] == ["fMRI"]
    assert Path(result.tables[0].path) == tmp_path / "features" / "fmri" / plan.plan_id / "fmri_features.csv"
    assert (tmp_path / "features" / "eeg").is_dir()
    assert (tmp_path / "features" / "scales").is_dir()
    assert (tmp_path / "features" / "dti").is_dir()
    assert (tmp_path / "features" / "mri").is_dir()
    assert not (tmp_path / "features" / "eeg" / plan.plan_id).exists()
    assert not (tmp_path / "features" / "scales" / plan.plan_id).exists()
    assert not (tmp_path / "features" / "dti" / plan.plan_id).exists()
    assert not (tmp_path / "features" / "mri" / plan.plan_id).exists()
    assert not (tmp_path / "features" / "eeg" / plan.plan_id / "eeg_features.csv").exists()


def test_feature_extraction_auto_adds_extra_modalities_when_configured(tmp_path):
    hypotheses = load_hypotheses("outputs/hypotheses/hypothesis_pool.json")
    profile = load_data_profile("outputs/profiles/analysis_ready_profile.yaml")
    plan = build_experiment_plan_from_hypothesis(hypotheses[0], profile)

    result = run_feature_extraction(
        {
            "output_root": str(tmp_path / "features"),
            "modalities": "auto",
            "fmri": {"features_csv": str(Path("data/fixtures/toy_fmri_features.csv").resolve())},
            "eeg": {"features_csv": str(Path("data/fixtures/toy_eeg_features.csv").resolve())},
            "scales": {"features_csv": str(Path("data/fixtures/toy_scale_features.csv").resolve())},
            "dti": {"features_csv": str(Path("data/fixtures/toy_dti_features.csv").resolve())},
        },
        plan,
    )

    assert sorted(table.modality for table in result.tables) == ["DTI", "EEG", "fMRI", "scales"]
    assert (tmp_path / "features" / "fmri" / plan.plan_id / "fmri_features.csv").exists()
    assert (tmp_path / "features" / "eeg" / plan.plan_id / "eeg_features.csv").exists()
    assert (tmp_path / "features" / "scales" / plan.plan_id / "scale_features.csv").exists()
    assert (tmp_path / "features" / "dti" / plan.plan_id / "dti_features.csv").exists()


def test_feature_extraction_extracts_non_fmri_raw_modalities(tmp_path):
    hypotheses = load_hypotheses("outputs/hypotheses/hypothesis_pool.json")
    profile = load_data_profile("outputs/profiles/analysis_ready_profile.yaml")
    plan = build_experiment_plan_from_hypothesis(hypotheses[0], profile)

    eeg_root = tmp_path / "raw_eeg" / "sub-001"
    eeg_root.mkdir(parents=True)
    (eeg_root / "sleep_eeg.csv").write_text("delta_power,theta_power\n1.0,0.5\n2.0,0.7\n", encoding="utf-8")
    scale_table = tmp_path / "scale_raw.csv"
    scale_table.write_text("participant_id,ISI,PSQI\nsub-001,18,12\n", encoding="utf-8")
    dti_table = tmp_path / "dti_raw.tsv"
    dti_table.write_text("subject_id\tthalamo_cortical_FA\tuncinate_FA\nsub-001\t0.41\t0.35\n", encoding="utf-8")

    result = run_feature_extraction(
        {
            "output_root": str(tmp_path / "features"),
            "modalities": "auto",
            "eeg": {"input_root": str(tmp_path / "raw_eeg")},
            "scales": {"raw_table": str(scale_table)},
            "dti": {"raw_table": str(dti_table)},
        },
        plan,
    )

    assert sorted(table.modality for table in result.tables) == ["DTI", "EEG", "scales"]
    assert Path(result.merged_features_path).exists()
    assert set(Path(table.path).name for table in result.tables) == {
        "dti_features.csv",
        "eeg_features.csv",
        "scale_features.csv",
    }
    assert (tmp_path / "features" / "eeg" / plan.plan_id / "eeg_features.csv").exists()
    assert (tmp_path / "features" / "scales" / plan.plan_id / "scale_features.csv").exists()
    assert (tmp_path / "features" / "dti" / plan.plan_id / "dti_features.csv").exists()
    merged = pd.read_csv(result.merged_features_path)
    assert merged["subject_id"].tolist() == ["sub-001"]
    assert {"eeg_delta_power", "scales_ISI", "dti_thalamo_cortical_FA"}.issubset(set(merged.columns))


def test_experiment_llm_enabled_accepts_inner_and_outer_config():
    inner = {
        "enabled": True,
        "provider": "ollama",
        "base_url": "http://localhost:11434",
        "model": "deepseek-coder-v2:16b",
    }
    assert experiment_llm_enabled(inner)
    assert experiment_llm_enabled({"llm": inner})
    assert build_experiment_llm(inner, task_name="test") is not None


def test_analysis_templates_do_not_inner_join_unrelated_modalities(tmp_path):
    fmri = tmp_path / "fmri_features.csv"
    fmri.write_text("subject_id,x,y\nsub-001,1,3\nsub-002,2,2\nsub-003,3,1\n", encoding="utf-8")
    eeg = tmp_path / "eeg_features.csv"
    eeg.write_text("subject_id,slow_wave_density\nother-001,0.1\nother-002,0.2\n", encoding="utf-8")
    plan = ExperimentPlan(
        plan_id="plan_join",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["x"],
        outcomes=["y"],
        variables=[
            ExperimentVariable(name="x", role=ExperimentVariableRole.predictor, modality="fMRI", source_file=str(fmri), source_column="x"),
            ExperimentVariable(name="y", role=ExperimentVariableRole.outcome, modality="fMRI", source_file=str(fmri), source_column="y"),
            ExperimentVariable(
                name="slow_wave_density",
                role=ExperimentVariableRole.covariate,
                modality="EEG",
                source_file=str(eeg),
                source_column="slow_wave_density",
            ),
        ],
        primary_tests=[{"test_id": "t1", "predictor": "x", "outcome": "y"}],
    )

    tests = run_primary_tests(plan)

    assert tests[0].n == 3
    assert tests[0].effect is not None


def test_analysis_templates_resolve_modality_prefixed_columns(tmp_path):
    multimodal = tmp_path / "multimodal_features.csv"
    multimodal.write_text(
        "subject_id,fmri_thalamus_DMN_FC,fmri_global_signal_psd_power_mean\nsub-001,1,1\nsub-002,2,3\nsub-003,3,5\n",
        encoding="utf-8",
    )
    plan = ExperimentPlan(
        plan_id="plan_prefixed",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["thalamus_DMN_FC"],
        outcomes=["global_signal_psd_power_mean"],
        variables=[
            ExperimentVariable(
                name="thalamus_DMN_FC",
                role=ExperimentVariableRole.predictor,
                modality="fMRI",
                source_file=str(multimodal),
                source_column="thalamus_DMN_FC",
            ),
            ExperimentVariable(
                name="global_signal_psd_power_mean",
                role=ExperimentVariableRole.outcome,
                modality="fMRI",
                source_file=str(multimodal),
                source_column="global_signal_psd_power_mean",
            ),
        ],
        primary_tests=[{"test_id": "t1", "predictor": "thalamus_DMN_FC", "outcome": "global_signal_psd_power_mean"}],
    )

    tests = run_primary_tests(plan)

    assert tests[0].n == 3
    assert tests[0].effect is not None


def test_testability_precheck_rebuilds_variables_for_available_fmri_only(tmp_path):
    fmri_file = tmp_path / "fmri_features.csv"
    fmri_file.write_text(
        "subject_id,thalamus_DMN_FC,salience_FC,global_signal_psd_power_mean,mean_FD\nsub-001,1,2,3,0.1\n",
        encoding="utf-8",
    )
    profile = DataProfile(
        profile_type="analysis_ready_profile",
        features=[
            FeatureProfile(
                feature_name="thalamus_DMN_FC",
                modality="fMRI",
                source_file=str(fmri_file),
                source_column="thalamus_DMN_FC",
                approved=True,
                role="feature",
                n_available=1,
            ),
            FeatureProfile(
                feature_name="salience_FC",
                modality="fMRI",
                source_file=str(fmri_file),
                source_column="salience_FC",
                approved=True,
                role="feature",
                n_available=1,
            ),
            FeatureProfile(
                feature_name="global_signal_psd_power_mean",
                modality="fMRI",
                source_file=str(fmri_file),
                source_column="global_signal_psd_power_mean",
                approved=True,
                role="negative_control",
                n_available=1,
            ),
            FeatureProfile(
                feature_name="mean_FD",
                modality="fMRI",
                source_file=str(fmri_file),
                source_column="mean_FD",
                approved=True,
                role="covariate",
                n_available=1,
            ),
        ],
    )
    plan = ExperimentPlan(
        plan_id="plan_available",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["FA", "thalamus_DMN_FC"],
        outcomes=["PSQI"],
        covariates=["medication"],
        variables=[
            ExperimentVariable(name="FA", role=ExperimentVariableRole.predictor, modality="DTI"),
            ExperimentVariable(name="thalamus_DMN_FC", role=ExperimentVariableRole.predictor, modality="fMRI"),
            ExperimentVariable(name="PSQI", role=ExperimentVariableRole.outcome, modality="scales"),
        ],
        metadata={"requested_modalities": ["DTI", "fMRI", "scales"]},
    )

    updated = TestabilityPrecheck().run(plan, profile)

    assert updated.predictors == ["thalamus_DMN_FC"]
    assert updated.outcomes == ["salience_FC"]
    assert updated.covariates == ["mean_FD"]
    assert updated.negative_controls == ["global_signal_psd_power_mean"]
    assert {variable.name for variable in updated.variables} == {
        "thalamus_DMN_FC",
        "salience_FC",
        "global_signal_psd_power_mean",
        "mean_FD",
    }
    assert {variable.modality.lower() for variable in updated.variables} == {"fmri"}
    assert "submechanism" not in updated.primary_tests[0]["question"].lower()
    assert updated.metadata["testability_precheck"]["mode"] == "single_fmri_proxy_analysis"


def test_testability_precheck_does_not_use_fmri_artifacts_as_primary_outcomes(tmp_path):
    fmri_file = tmp_path / "fmri_features.csv"
    fmri_file.write_text("subject_id,thalamus_DMN_FC,global_signal_psd_power_mean,mean_FD\nsub-001,1,2,0.1\n", encoding="utf-8")
    profile = DataProfile(
        profile_type="analysis_ready_profile",
        features=[
            FeatureProfile(
                feature_name="thalamus_DMN_FC",
                modality="fMRI",
                source_file=str(fmri_file),
                source_column="thalamus_DMN_FC",
                approved=True,
                role="feature",
                n_available=1,
            ),
            FeatureProfile(
                feature_name="global_signal_psd_power_mean",
                modality="fMRI",
                source_file=str(fmri_file),
                source_column="global_signal_psd_power_mean",
                approved=True,
                role="negative_control",
                n_available=1,
            ),
            FeatureProfile(
                feature_name="mean_FD",
                modality="fMRI",
                source_file=str(fmri_file),
                source_column="mean_FD",
                approved=True,
                role="covariate",
                n_available=1,
            ),
        ],
    )
    plan = ExperimentPlan(
        plan_id="plan_artifact_only",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["thalamus_DMN_FC"],
        outcomes=["PSQI"],
        variables=[
            ExperimentVariable(name="thalamus_DMN_FC", role=ExperimentVariableRole.predictor, modality="fMRI"),
            ExperimentVariable(name="PSQI", role=ExperimentVariableRole.outcome, modality="scales"),
        ],
        metadata={"requested_modalities": ["fMRI", "scales"]},
    )

    updated = TestabilityPrecheck().run(plan, profile)

    assert updated.predictors == ["thalamus_DMN_FC"]
    assert updated.outcomes == []
    assert updated.primary_tests == []
    assert updated.negative_controls == ["global_signal_psd_power_mean"]
    assert updated.metadata["testability_precheck"]["mode"] == "single_fmri_not_testable"
