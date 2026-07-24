from pathlib import Path

import pandas as pd

from sleep_ai_scientist.common.io import read_json, write_yaml
from sleep_ai_scientist.experiment.agents.llm_adapter import build_experiment_llm, experiment_llm_enabled
from sleep_ai_scientist.experiment.agents.analysis_templates import run_primary_tests
from sleep_ai_scientist.experiment.agents.experiment_design_agent import ExperimentDesignAgent
from sleep_ai_scientist.experiment.agents.statistical_model_agent import StatisticalModelAgent
from sleep_ai_scientist.experiment.visualization import render_experiment_visualizations
from sleep_ai_scientist.experiment.agents.planning import build_experiment_plan_from_hypothesis, load_data_profile, load_hypotheses
from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline
from sleep_ai_scientist.feature_extraction.feature_pipeline import run_feature_extraction
from sleep_ai_scientist.feature_extraction.profile_builder import TestabilityPrecheck
from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.hypothesis.testability import annotate_registry_testability
from sleep_ai_scientist.schemas.data_profile import DataProfile, FeatureProfile
from sleep_ai_scientist.schemas.experiment import ExperimentPlan, ExperimentResultBundle, ExperimentVariable, ExperimentVariableRole
from sleep_ai_scientist.schemas.hypothesis import HypothesisStatus


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


def test_experiment_design_uses_current_data_testability_priority(tmp_path):
    registry = HypothesisRegistry(session_id="experiment_priority_session")
    dti = registry.add_hypothesis(
        title="White Matter FA Mechanism",
        summary="DTI fractional anisotropy may explain insomnia.",
        content="Fractional anisotropy and white matter integrity are central.",
        rationale="FA requires DTI.",
        experimental_plan="Measure FA from DTI.",
        generation_strategy="literature_exploration",
        elo_rating=1510,
        status=HypothesisStatus.active,
    )
    fmri = registry.add_hypothesis(
        title="DMN Functional Connectivity Mechanism",
        summary="fMRI DMN_FC and salience_FC may explain insomnia.",
        content="Resting-state fMRI functional connectivity is central.",
        rationale="DMN_FC is available.",
        experimental_plan="Use fMRI DMN_FC and salience_FC.",
        generation_strategy="literature_exploration",
        elo_rating=1450,
        status=HypothesisStatus.active,
    )
    profile = DataProfile(
        profile_type="analysis_ready_profile",
        features=[
            FeatureProfile(feature_name="DMN_FC", modality="fMRI", source_file="fmri.csv", source_column="DMN_FC", approved=True, role="feature"),
            FeatureProfile(feature_name="salience_FC", modality="fMRI", source_file="fmri.csv", source_column="salience_FC", approved=True, role="feature"),
        ],
    )
    annotate_registry_testability(registry, profile)
    registry.write_outputs(tmp_path / "hypotheses", top_k=2)
    profile_path = tmp_path / "analysis_ready_profile.yaml"
    write_yaml(profile_path, profile.model_dump(mode="json"))

    plans = ExperimentDesignAgent({"llm": {"enabled": False}}, output_dir=tmp_path / "plans").run(
        hypothesis_pool_path=tmp_path / "hypotheses" / "hypothesis_pool.json",
        data_profile_path=profile_path,
        approved_variables_path=None,
        variable_mapping_path=None,
        top_k=1,
    )

    assert registry.hypotheses[dti.hypothesis_id].metadata["data_testability"]["status"] == "not_directly_testable"
    assert plans[0].hypothesis_id == fmri.hypothesis_id
    assert plans[0].metadata["hypothesis_data_testability"]["status"] == "directly_testable"


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
    assert {item["modality"] for item in summary["feature_tables"]} == {"fMRI", "EEG", "scales"}
    assert all(Path(item["path"]).exists() for item in summary["feature_tables"])
    assert summary["feature_profiles"]
    assert summary["merged_feature_tables"]
    assert Path(summary["visualizations"]["html"]).exists()
    assert Path(summary["visualizations"]["manifest"]).exists()
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


def test_analysis_templates_run_linear_regression_template(tmp_path):
    features = tmp_path / "linear_features.csv"
    features.write_text(
        "subject_id,x,y,age\n"
        "sub-001,1,3,20\n"
        "sub-002,2,5,21\n"
        "sub-003,3,7,22\n"
        "sub-004,4,9,23\n"
        "sub-005,5,11,24\n",
        encoding="utf-8",
    )
    plan = ExperimentPlan(
        plan_id="plan_linear",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["x"],
        outcomes=["y"],
        covariates=["age"],
        variables=[
            ExperimentVariable(name="x", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x"),
            ExperimentVariable(name="y", role=ExperimentVariableRole.outcome, source_file=str(features), source_column="y"),
            ExperimentVariable(name="age", role=ExperimentVariableRole.covariate, source_file=str(features), source_column="age"),
        ],
        primary_tests=[{"test_id": "linear_t1", "predictor": "x", "outcome": "y", "model": "linear_regression"}],
    )

    tests = run_primary_tests(plan, primary_template="linear_regression")

    assert tests[0].method == "linear_regression"
    assert tests[0].effect is not None
    assert tests[0].p_value is not None
    assert tests[0].passed
    assert tests[0].metadata["r_squared"] > 0.99
    assert "Intercept" in tests[0].metadata["coefficients"]


def test_analysis_templates_run_mixed_effects_template(tmp_path):
    features = tmp_path / "mixed_features.csv"
    features.write_text(
        "subject_id,site,x,y\n"
        "sub-001,A,1,2\n"
        "sub-002,A,2,4\n"
        "sub-003,A,3,6\n"
        "sub-004,B,1,3\n"
        "sub-005,B,2,5\n"
        "sub-006,B,3,7\n",
        encoding="utf-8",
    )
    plan = ExperimentPlan(
        plan_id="plan_mixed",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["x"],
        outcomes=["y"],
        covariates=["site"],
        variables=[
            ExperimentVariable(name="x", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x"),
            ExperimentVariable(name="y", role=ExperimentVariableRole.outcome, source_file=str(features), source_column="y"),
            ExperimentVariable(name="site", role=ExperimentVariableRole.covariate, source_file=str(features), source_column="site"),
        ],
        primary_tests=[{"test_id": "mixed_t1", "predictor": "x", "outcome": "y", "model": "mixed_effects", "group": "site"}],
    )

    tests = run_primary_tests(plan, primary_template="mixed_effects")

    assert tests[0].method == "mixed_effects"
    assert tests[0].effect is not None
    assert tests[0].metadata["group_variable"] == "site"
    assert "x" in tests[0].metadata["fixed_effects"]


def test_analysis_templates_run_logistic_regression_template(tmp_path):
    features = tmp_path / "logistic_features.csv"
    features.write_text(
        "subject_id,x,y_bin,mean_FD\n"
        "sub-001,0.1,0,0.01\n"
        "sub-002,0.2,0,0.02\n"
        "sub-003,0.3,1,0.03\n"
        "sub-004,0.8,0,0.02\n"
        "sub-005,0.9,1,0.01\n"
        "sub-006,1.0,0,0.02\n"
        "sub-007,1.1,1,0.03\n"
        "sub-008,1.2,1,0.01\n",
        encoding="utf-8",
    )
    plan = ExperimentPlan(
        plan_id="plan_logistic",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["x"],
        outcomes=["y_bin"],
        covariates=["mean_FD"],
        variables=[
            ExperimentVariable(name="x", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x"),
            ExperimentVariable(name="y_bin", role=ExperimentVariableRole.outcome, source_file=str(features), source_column="y_bin"),
            ExperimentVariable(name="mean_FD", role=ExperimentVariableRole.covariate, source_file=str(features), source_column="mean_FD"),
        ],
        primary_tests=[{"test_id": "logistic_t1", "predictor": "x", "outcome": "y_bin", "model": "logistic_regression"}],
    )

    tests = run_primary_tests(plan, primary_template="logistic_regression")

    assert tests[0].method == "logistic_regression"
    assert tests[0].n == 8
    assert tests[0].metadata["covariates"] == ["mean_FD"]
    assert "odds_ratios" in tests[0].metadata


def test_statistical_model_agent_auto_selects_model_from_data_paradigm_and_logs(tmp_path, capsys):
    fmri = tmp_path / "fmri_model_select.csv"
    fmri.write_text(
        "subject_id,DMN_FC,salience_FC,mean_FD\n"
        "sub-001,1,2,0.10\n"
        "sub-002,2,3,0.20\n"
        "sub-003,3,5,0.15\n"
        "sub-004,4,7,0.30\n"
        "sub-005,5,11,0.25\n"
        "sub-006,6,13,0.35\n",
        encoding="utf-8",
    )
    plan = ExperimentPlan(
        plan_id="plan_auto_fmri_motion",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["DMN_FC"],
        outcomes=["salience_FC"],
        covariates=["mean_FD"],
        variables=[
            ExperimentVariable(name="DMN_FC", role=ExperimentVariableRole.predictor, modality="fMRI", source_file=str(fmri), source_column="DMN_FC"),
            ExperimentVariable(name="salience_FC", role=ExperimentVariableRole.outcome, modality="fMRI", source_file=str(fmri), source_column="salience_FC"),
            ExperimentVariable(name="mean_FD", role=ExperimentVariableRole.covariate, modality="fMRI", source_file=str(fmri), source_column="mean_FD"),
        ],
        primary_tests=[{"test_id": "auto_t1", "predictor": "DMN_FC", "outcome": "salience_FC"}],
    )
    agent = StatisticalModelAgent({"llm": {"enabled": False}, "primary_template": "auto", "verbose": True}, output_dir=tmp_path / "traces")

    stats_result, _, _, _, trace = agent.run(plan, bootstrap_iterations=5)

    assert stats_result.tests[0].method == "linear_regression"
    assert trace["model_selection_policy"]["primary_template"] == "linear_regression"
    assert "covariate" in trace["model_selection_policy"]["reason"].lower()
    captured = capsys.readouterr()
    assert "[experiment:model_selection]" in captured.out
    assert "primary=linear_regression" in captured.out


def test_statistical_model_agent_auto_selects_mixed_and_logistic_templates(tmp_path):
    grouped = tmp_path / "grouped_model_select.csv"
    grouped.write_text(
        "subject_id,site,x,y\n"
        "sub-001,A,1,2\n"
        "sub-002,A,2,3\n"
        "sub-003,A,3,4\n"
        "sub-004,B,1,3\n"
        "sub-005,B,2,5\n"
        "sub-006,B,3,7\n",
        encoding="utf-8",
    )
    grouped_plan = ExperimentPlan(
        plan_id="plan_auto_mixed",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["x"],
        outcomes=["y"],
        covariates=["site"],
        variables=[
            ExperimentVariable(name="x", role=ExperimentVariableRole.predictor, source_file=str(grouped), source_column="x"),
            ExperimentVariable(name="y", role=ExperimentVariableRole.outcome, source_file=str(grouped), source_column="y"),
            ExperimentVariable(name="site", role=ExperimentVariableRole.covariate, source_file=str(grouped), source_column="site"),
        ],
        primary_tests=[{"test_id": "auto_mixed_t1", "predictor": "x", "outcome": "y", "group": "site"}],
    )
    binary = tmp_path / "binary_model_select.csv"
    binary.write_text(
        "subject_id,x,y_bin\n"
        "sub-001,0,0\nsub-002,1,0\nsub-003,2,1\nsub-004,3,0\nsub-005,4,1\nsub-006,5,1\nsub-007,6,0\nsub-008,7,1\n",
        encoding="utf-8",
    )
    binary_plan = ExperimentPlan(
        plan_id="plan_auto_logistic",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["x"],
        outcomes=["y_bin"],
        variables=[
            ExperimentVariable(name="x", role=ExperimentVariableRole.predictor, source_file=str(binary), source_column="x"),
            ExperimentVariable(name="y_bin", role=ExperimentVariableRole.outcome, source_file=str(binary), source_column="y_bin"),
        ],
        primary_tests=[{"test_id": "auto_logistic_t1", "predictor": "x", "outcome": "y_bin"}],
    )
    agent = StatisticalModelAgent({"llm": {"enabled": False}, "primary_template": "auto"}, output_dir=tmp_path / "traces")

    grouped_result, _, _, _, grouped_trace = agent.run(grouped_plan, bootstrap_iterations=5)
    binary_result, _, _, _, binary_trace = agent.run(binary_plan, bootstrap_iterations=5)

    assert grouped_trace["model_selection_policy"]["primary_template"] == "mixed_effects"
    assert grouped_result.tests[0].method == "mixed_effects"
    assert binary_trace["model_selection_policy"]["primary_template"] == "logistic_regression"
    assert binary_result.tests[0].method == "logistic_regression"


def test_statistical_model_agent_auto_runs_ml_from_model_selection_policy(tmp_path, capsys):
    features = tmp_path / "auto_all_models.csv"
    features.write_text(
        "subject_id,x1,x2,y_bin\n"
        "sub-001,0,1,0\n"
        "sub-002,1,1,0\n"
        "sub-003,2,2,1\n"
        "sub-004,3,2,0\n"
        "sub-005,4,3,1\n"
        "sub-006,5,4,1\n"
        "sub-007,6,4,0\n"
        "sub-008,7,5,1\n",
        encoding="utf-8",
    )
    plan = ExperimentPlan(
        plan_id="plan_auto_all_models",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["x1", "x2"],
        outcomes=["y_bin"],
        variables=[
            ExperimentVariable(name="x1", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x1"),
            ExperimentVariable(name="x2", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x2"),
            ExperimentVariable(name="y_bin", role=ExperimentVariableRole.outcome, source_file=str(features), source_column="y_bin"),
        ],
        primary_tests=[{"test_id": "auto_all_models_t1", "predictor": "x1", "outcome": "y_bin"}],
    )
    agent = StatisticalModelAgent(
        {
            "llm": {"enabled": False},
            "primary_template": "auto",
            "ml_models": ["logistic_regression", "decision_tree", "random_forest"],
            "ml_cv_folds": 3,
            "verbose": True,
        },
        output_dir=tmp_path / "traces",
    )

    stats_result, ml_result, _, _, trace = agent.run(plan, bootstrap_iterations=5)

    assert stats_result.tests[0].method == "logistic_regression"
    assert trace["model_selection_policy"]["run_ml"]
    assert trace["controlled_templates"]["ml_enabled_by_policy"]
    assert ml_result is not None
    assert ml_result.metadata["task_type"] == "classification"
    assert set(ml_result.metadata["models"]) == {"logistic_regression", "decision_tree_classifier", "random_forest_classifier"}
    captured = capsys.readouterr()
    assert "ml=enabled" in captured.out


def test_statistical_model_agent_runs_tree_ml_models_when_enabled(tmp_path):
    features = tmp_path / "ml_features.csv"
    features.write_text(
        "subject_id,x1,x2,y\n"
        "sub-001,0,1,0\n"
        "sub-002,1,1,1\n"
        "sub-003,2,1,2\n"
        "sub-004,3,2,3\n"
        "sub-005,4,3,4\n"
        "sub-006,5,5,5\n",
        encoding="utf-8",
    )
    plan = ExperimentPlan(
        plan_id="plan_ml",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["x1", "x2"],
        outcomes=["y"],
        variables=[
            ExperimentVariable(name="x1", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x1"),
            ExperimentVariable(name="x2", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x2"),
            ExperimentVariable(name="y", role=ExperimentVariableRole.outcome, source_file=str(features), source_column="y"),
        ],
        primary_tests=[{"test_id": "ml_t1", "predictor": "x1", "outcome": "y"}],
    )
    agent = StatisticalModelAgent(
        {"llm": {"enabled": False}, "ml_models": ["decision_tree", "random_forest"], "ml_cv_folds": 3},
        output_dir=tmp_path / "traces",
    )

    _, ml_result, _, _, _ = agent.run(plan, bootstrap_iterations=5)

    assert ml_result is not None
    assert ml_result.model_type == "decision_tree_regressor,random_forest_regressor"
    assert ml_result.cv_folds == 3
    assert ml_result.score_name == "r2"
    assert ml_result.score_mean is not None
    assert set(ml_result.feature_importance) == {"x1", "x2"}
    assert ml_result.metadata["models"]["decision_tree_regressor"]["feature_importance"]
    assert ml_result.metadata["models"]["random_forest_regressor"]["feature_importance"]


def test_statistical_model_agent_runs_all_requested_ml_models_for_classification_and_regression(tmp_path):
    features = tmp_path / "all_ml_features.csv"
    features.write_text(
        "subject_id,x1,x2,y_cont,y_bin\n"
        "sub-001,0,1,0.1,0\n"
        "sub-002,1,1,1.0,0\n"
        "sub-003,2,2,2.1,0\n"
        "sub-004,3,3,3.2,1\n"
        "sub-005,4,3,4.1,1\n"
        "sub-006,5,4,5.2,1\n"
        "sub-007,6,5,6.1,1\n"
        "sub-008,7,5,7.3,1\n",
        encoding="utf-8",
    )
    variables = [
        ExperimentVariable(name="x1", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x1"),
        ExperimentVariable(name="x2", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x2"),
    ]
    reg_plan = ExperimentPlan(
        plan_id="plan_all_ml_reg",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["x1", "x2"],
        outcomes=["y_cont"],
        variables=[*variables, ExperimentVariable(name="y_cont", role=ExperimentVariableRole.outcome, source_file=str(features), source_column="y_cont")],
        primary_tests=[{"test_id": "reg_t1", "predictor": "x1", "outcome": "y_cont"}],
    )
    cls_plan = ExperimentPlan(
        plan_id="plan_all_ml_cls",
        hypothesis_id="hyp",
        hypothesis_title="H",
        scientific_question="Q",
        predictors=["x1", "x2"],
        outcomes=["y_bin"],
        variables=[*variables, ExperimentVariable(name="y_bin", role=ExperimentVariableRole.outcome, source_file=str(features), source_column="y_bin")],
        primary_tests=[{"test_id": "cls_t1", "predictor": "x1", "outcome": "y_bin"}],
    )
    config = {
        "llm": {"enabled": False},
        "primary_template": "spearman_correlation",
        "ml_models": ["logistic_regression", "decision_tree", "random_forest", "svm", "xgboost", "lightgbm"],
        "ml_cv_folds": 4,
    }
    agent = StatisticalModelAgent(config, output_dir=tmp_path / "traces")

    _, reg_result, _, _, _ = agent.run(reg_plan, bootstrap_iterations=5)
    _, cls_result, _, _, _ = agent.run(cls_plan, bootstrap_iterations=5)

    assert reg_result is not None
    assert reg_result.metadata["task_type"] == "regression"
    assert set(reg_result.metadata["models"]) == {"decision_tree_regressor", "random_forest_regressor", "svm_regressor", "xgboost_regressor", "lightgbm_regressor"}
    assert reg_result.score_name == "r2"
    assert cls_result is not None
    assert cls_result.metadata["task_type"] == "classification"
    assert set(cls_result.metadata["models"]) == {
        "logistic_regression",
        "decision_tree_classifier",
        "random_forest_classifier",
        "svm_classifier",
        "xgboost_classifier",
        "lightgbm_classifier",
    }
    assert cls_result.score_name == "roc_auc"
    assert cls_result.metadata["models"]["logistic_regression"]["coefficients"]


def test_experiment_visualization_renders_model_specific_outputs(tmp_path):
    features = tmp_path / "viz_features.csv"
    features.write_text(
        "subject_id,x1,x2,y,control\n"
        "sub-001,0,1,0,5\n"
        "sub-002,1,1,1,4\n"
        "sub-003,2,1,2,3\n"
        "sub-004,3,2,3,2\n"
        "sub-005,4,3,4,1\n"
        "sub-006,5,5,5,0\n",
        encoding="utf-8",
    )
    plan = ExperimentPlan(
        plan_id="plan_viz",
        hypothesis_id="hyp",
        hypothesis_title="Visualization Hypothesis",
        scientific_question="Q",
        predictors=["x1", "x2"],
        outcomes=["y"],
        negative_controls=["control"],
        variables=[
            ExperimentVariable(name="x1", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x1"),
            ExperimentVariable(name="x2", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x2"),
            ExperimentVariable(name="y", role=ExperimentVariableRole.outcome, source_file=str(features), source_column="y"),
            ExperimentVariable(name="control", role=ExperimentVariableRole.negative_control, source_file=str(features), source_column="control"),
        ],
        primary_tests=[{"test_id": "viz_t1", "predictor": "x1", "outcome": "y", "model": "linear_regression"}],
    )
    agent = StatisticalModelAgent(
        {"llm": {"enabled": False}, "primary_template": "linear_regression", "ml_models": ["decision_tree"], "ml_cv_folds": 3},
        output_dir=tmp_path / "traces",
    )
    stats_result, ml_result, robustness, negative_controls, model_trace = agent.run(plan, bootstrap_iterations=5)
    bundle = ExperimentResultBundle(
        plan=plan,
        stats_result=stats_result,
        ml_result=ml_result,
        robustness_results=robustness,
        negative_control_results=negative_controls,
        metadata={"model_trace": model_trace},
    )

    manifest = render_experiment_visualizations([bundle], tmp_path / "visuals")

    assert Path(manifest["html"]).exists()
    assert Path(manifest["manifest"]).exists()
    assert any("primary_test_matrix" in Path(path).name for path in manifest["figures"])
    assert any("linear_regression_fit" in Path(path).name for path in manifest["figures"])
    assert any("ml_feature_importance" in Path(path).name for path in manifest["figures"])


def test_experiment_visualization_cleans_stale_figures_and_adds_readable_metadata(tmp_path):
    features = tmp_path / "viz_long_features.csv"
    features.write_text(
        "subject_id,timefreq_fALFF_0.01_0.08_over_0.01_0.25,salience_FC,global_signal_psd_power_mean\n"
        "sub-001,0.0,0.0,3\n"
        "sub-002,0.5,0.2,2\n"
        "sub-003,0.7,0.9,1\n"
        "sub-004,0.8,1.2,0\n",
        encoding="utf-8",
    )
    plan = ExperimentPlan(
        plan_id="experiment_plan_long_labels",
        hypothesis_id="hyp",
        hypothesis_title="Visualization Hypothesis",
        scientific_question="Q",
        predictors=["timefreq_fALFF_0.01_0.08_over_0.01_0.25"],
        outcomes=["salience_FC"],
        negative_controls=["global_signal_psd_power_mean"],
        variables=[
            ExperimentVariable(
                name="timefreq_fALFF_0.01_0.08_over_0.01_0.25",
                role=ExperimentVariableRole.predictor,
                source_file=str(features),
                source_column="timefreq_fALFF_0.01_0.08_over_0.01_0.25",
            ),
            ExperimentVariable(name="salience_FC", role=ExperimentVariableRole.outcome, source_file=str(features), source_column="salience_FC"),
            ExperimentVariable(
                name="global_signal_psd_power_mean",
                role=ExperimentVariableRole.negative_control,
                source_file=str(features),
                source_column="global_signal_psd_power_mean",
            ),
        ],
        primary_tests=[
            {
                "test_id": "experiment_plan_long_labels_timefreq_fALFF_0.01_0.08_over_0.01_0.25_salience_FC",
                "predictor": "timefreq_fALFF_0.01_0.08_over_0.01_0.25",
                "outcome": "salience_FC",
            }
        ],
    )
    agent = StatisticalModelAgent({"llm": {"enabled": False}}, output_dir=tmp_path / "traces")
    stats_result, _, robustness, negative_controls, model_trace = agent.run(plan, bootstrap_iterations=5)
    bundle = ExperimentResultBundle(
        plan=plan,
        stats_result=stats_result,
        robustness_results=robustness,
        negative_control_results=negative_controls,
        metadata={"model_trace": model_trace},
    )
    visuals = tmp_path / "visuals"
    stale = visuals / "figures" / "old_experiment_plan.png"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    manifest = render_experiment_visualizations([bundle], visuals)

    assert not stale.exists()
    assert manifest["figures"]
    assert manifest["figure_records"]
    assert all(Path(record["path"]).exists() for record in manifest["figure_records"])
    assert any(record["kind"] == "spearman_scatter" and "Full variable pair:" in record["caption"] for record in manifest["figure_records"])
    assert any(record["kind"] == "negative_controls" and "green=passed negative control" in record["caption"] for record in manifest["figure_records"])
    html = Path(manifest["html"]).read_text(encoding="utf-8")
    assert "timefreq fALFF" in html
    assert "Full variable pair:" in html
    assert "failed negative control" in html


def test_experiment_visualization_renders_ml_classification_and_regression_diagnostics(tmp_path):
    features = tmp_path / "viz_ml_features.csv"
    features.write_text(
        "subject_id,x1,x2,y_bin\n"
        "sub-001,0,1,0\n"
        "sub-002,1,1,0\n"
        "sub-003,2,2,1\n"
        "sub-004,3,3,0\n"
        "sub-005,4,3,1\n"
        "sub-006,5,4,1\n",
        encoding="utf-8",
    )
    plan = ExperimentPlan(
        plan_id="plan_viz_ml_cls",
        hypothesis_id="hyp",
        hypothesis_title="ML Visualization Hypothesis",
        scientific_question="Q",
        predictors=["x1", "x2"],
        outcomes=["y_bin"],
        variables=[
            ExperimentVariable(name="x1", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x1"),
            ExperimentVariable(name="x2", role=ExperimentVariableRole.predictor, source_file=str(features), source_column="x2"),
            ExperimentVariable(name="y_bin", role=ExperimentVariableRole.outcome, source_file=str(features), source_column="y_bin"),
        ],
        primary_tests=[{"test_id": "viz_ml_t1", "predictor": "x1", "outcome": "y_bin"}],
    )
    agent = StatisticalModelAgent(
        {"llm": {"enabled": False}, "ml_models": ["logistic_regression", "decision_tree", "random_forest", "svm", "xgboost", "lightgbm"], "ml_cv_folds": 3},
        output_dir=tmp_path / "traces",
    )
    stats_result, ml_result, robustness, negative_controls, model_trace = agent.run(plan, bootstrap_iterations=5)
    bundle = ExperimentResultBundle(
        plan=plan,
        stats_result=stats_result,
        ml_result=ml_result,
        robustness_results=robustness,
        negative_control_results=negative_controls,
        metadata={"model_trace": model_trace},
    )

    manifest = render_experiment_visualizations([bundle], tmp_path / "visuals")

    assert any("ml_feature_importance" in Path(path).name for path in manifest["figures"])
    assert any("ml_classification_confusion" in Path(path).name for path in manifest["figures"])
    assert any("ml_classification_roc" in Path(path).name for path in manifest["figures"])


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
