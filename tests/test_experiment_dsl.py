from pathlib import Path

from sleep_ai_scientist.common.io import read_json, write_yaml
from sleep_ai_scientist.experiment.agents.llm import build_experiment_llm, experiment_llm_enabled
from sleep_ai_scientist.experiment.agents.planning import build_experiment_plan_from_hypothesis, load_data_profile, load_hypotheses
from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline
from sleep_ai_scientist.feature_extraction.feature_pipeline import run_feature_extraction


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
    assert list(feature_root.glob("*/analysis_ready_profile.yaml"))
    assert list(feature_root.glob("*/multimodal_features.csv"))
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
