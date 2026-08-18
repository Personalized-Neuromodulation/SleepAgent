from __future__ import annotations

from pathlib import Path

from sleep_ai_scientist.experiment import experiment_pipeline
from sleep_ai_scientist.feature_extraction.schemas import FeatureExtractionResult
from sleep_ai_scientist.schemas.data_profile import DataProfile
from sleep_ai_scientist.schemas.experiment import ExperimentPlan


def test_experiment_pipeline_extracts_features_before_design(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "experiment_config.yaml"
    initial_profile = tmp_path / "initial_profile.yaml"
    extracted_profile = tmp_path / "features" / "profile" / "pre_experiment" / "analysis_ready_profile.yaml"
    merged_features = tmp_path / "features" / "multimodal" / "pre_experiment" / "multimodal_features.csv"
    config.write_text(
        "experiment:\n"
        "  verbose: false\n"
        "feature_extraction:\n"
        "  enabled: true\n"
        f"  output_root: {tmp_path / 'features'}\n"
        "  modalities:\n"
        "    - scales\n"
        "  scales:\n"
        f"    input_root: {tmp_path / 'sourcedata'}\n"
        "paths:\n"
        f"  data_profile: {initial_profile}\n"
        f"  experiment_output_dir: {tmp_path / 'experiments'}\n"
        f"  experiment_results: {tmp_path / 'experiments' / 'results.json'}\n"
        f"  experimental_feedback: {tmp_path / 'experiments' / 'feedback.json'}\n"
        f"  experiment_report: {tmp_path / 'experiments' / 'report.md'}\n"
        f"  experiment_visualizations: {tmp_path / 'experiments' / 'visuals'}\n",
        encoding="utf-8",
    )
    calls: list[tuple[str, str]] = []

    def fake_run_feature_extraction(feature_config, plan):
        calls.append(("feature_extraction", plan.plan_id))
        return FeatureExtractionResult(
            plan_id=plan.plan_id,
            output_dir=str(tmp_path / "features"),
            tables=[],
            profile_path=str(extracted_profile),
            merged_features_path=str(merged_features),
        )

    def fake_load_data_profile(path):
        calls.append(("load_profile", str(path)))
        return DataProfile(profile_type="analysis_ready_profile", features=[])

    class FakeDesignAgent:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, *args, data_profile_path, **kwargs):
            calls.append(("design", str(data_profile_path)))
            return []

    monkeypatch.setattr(experiment_pipeline, "run_feature_extraction", fake_run_feature_extraction)
    monkeypatch.setattr(experiment_pipeline, "load_data_profile", fake_load_data_profile)
    monkeypatch.setattr(experiment_pipeline, "ExperimentDesignAgent", FakeDesignAgent)
    monkeypatch.setattr(experiment_pipeline, "render_experiment_visualizations", lambda *args, **kwargs: {})

    result = experiment_pipeline.run_experiment_pipeline(config)

    assert calls[:3] == [
        ("feature_extraction", "pre_experiment_features"),
        ("load_profile", str(extracted_profile)),
        ("design", str(extracted_profile)),
    ]
    assert result["feature_profiles"] == [str(extracted_profile)]
    assert result["merged_feature_tables"] == [str(merged_features)]
