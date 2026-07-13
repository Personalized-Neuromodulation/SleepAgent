from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_yaml, write_json
from sleep_ai_scientist.data_processing.fmri_local_split import run_fmri_local_split
from sleep_ai_scientist.experiment.agents.experiment_design_agent import ExperimentDesignAgent
from sleep_ai_scientist.experiment.agents.feedback_builder import build_experimental_feedback
from sleep_ai_scientist.experiment.agents.planning import load_data_profile
from sleep_ai_scientist.experiment.agents.result_review_agent import ResultReviewAgent
from sleep_ai_scientist.experiment.agents.statistical_model_agent import StatisticalModelAgent
from sleep_ai_scientist.experiment.agents.variable_mapping_agent import VariableMappingAgent
from sleep_ai_scientist.feature_extraction.feature_pipeline import run_feature_extraction
from sleep_ai_scientist.feature_extraction.profile_builder import TestabilityPrecheck
from sleep_ai_scientist.schemas.experiment import ExperimentResultBundle


def run_experiment_pipeline(config_path_value: str | Path = "configs/experiment_config.yaml") -> dict[str, Any]:
    config_path = Path(config_path_value)
    config = read_yaml(config_path)
    experiment_config = config.get("experiment", {})
    paths = config.get("paths", {})
    verbose = bool(experiment_config.get("verbose", True))

    output_dir = Path(paths.get("experiment_output_dir", "outputs/experiments"))
    trace_dir = output_dir / "agent_traces"
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir.mkdir(parents=True, exist_ok=True)

    _log(verbose, f"start config={config_path}")
    data_profile_path = Path(paths.get("data_profile", paths.get("design_data_profile", "outputs/profiles/analysis_ready_profile.yaml")))
    data_profile = load_data_profile(data_profile_path)
    _log(verbose, f"loaded data_profile={data_profile_path} features={len(data_profile.features)}")

    design_agent = ExperimentDesignAgent(experiment_config, output_dir=trace_dir)
    plans = design_agent.run(
        hypothesis_pool_path=paths.get("hypothesis_pool", "outputs/hypotheses/hypothesis_pool.json"),
        data_profile_path=data_profile_path,
        approved_variables_path=paths.get("approved_variables"),
        variable_mapping_path=paths.get("variable_mapping"),
        top_k=int(experiment_config.get("top_k_hypotheses", 1)),
    )
    _log(verbose, f"ExperimentDesignAgent done plans={len(plans)}")

    mapping_agent = VariableMappingAgent(experiment_config, output_dir=trace_dir)
    statistical_agent = StatisticalModelAgent(experiment_config, output_dir=trace_dir)
    review_agent = ResultReviewAgent(experiment_config, output_dir=trace_dir)

    bundles: list[ExperimentResultBundle] = []
    feedback_records: list[dict[str, Any]] = []
    for idx, plan in enumerate(plans, start=1):
        data_processing_result = None
        if bool(config.get("data_processing", {}).get("enabled", False)):
            processing_config = dict(config.get("data_processing", {}))
            backend = str(processing_config.get("backend", "fmri_local_split"))
            if backend != "fmri_local_split":
                raise ValueError(f"Unsupported data_processing backend: {backend}")
            _log(verbose, f"plan {idx}/{len(plans)} data processing backend={backend}")
            data_processing_result = run_fmri_local_split(processing_config)
            if data_processing_result.returncode != 0:
                raise RuntimeError(f"fmri_local_split failed with returncode={data_processing_result.returncode}")
            feature_config = dict(config.get("feature_extraction", {}))
            fmri_config = dict(feature_config.get("fmri", {}))
            fmri_config.setdefault("output_root", data_processing_result.output_root)
            fmri_config.setdefault("derivatives_root", data_processing_result.derivatives_root)
            fmri_config.setdefault("subjects", processing_config.get("subjects", []))
            feature_config["fmri"] = fmri_config
            config["feature_extraction"] = feature_config
            _log(verbose, f"DataProcessing done subjects={len(data_processing_result.processed_subjects)} output={data_processing_result.output_root}")
        if bool(config.get("feature_extraction", {}).get("enabled", False)):
            _log(verbose, f"plan {idx}/{len(plans)} feature extraction plan_id={plan.plan_id}")
            feature_result = run_feature_extraction(config.get("feature_extraction", {}), plan)
            data_profile = load_data_profile(feature_result.profile_path)
            plan = TestabilityPrecheck().run(plan, data_profile)
            _log(
                verbose,
                f"FeatureExtraction done tables={len(feature_result.tables)} profile_features={len(data_profile.features)}",
            )
        _log(verbose, f"plan {idx}/{len(plans)} mapping plan_id={plan.plan_id}")
        mapped_plan = mapping_agent.run(plan, data_profile)
        _log(verbose, f"plan {idx}/{len(plans)} statistics tests={len(mapped_plan.primary_tests)}")
        stats_result, ml_result, robustness, negative_controls, model_trace = statistical_agent.run(
            mapped_plan,
            enable_ml=bool(experiment_config.get("enable_ml", False)),
            bootstrap_iterations=int(experiment_config.get("bootstrap_iterations", 100)),
        )
        bundle = ExperimentResultBundle(
            plan=mapped_plan,
            stats_result=stats_result,
            ml_result=ml_result,
            robustness_results=robustness,
            negative_control_results=negative_controls,
            metadata={"model_trace": model_trace},
        )
        findings, evidence_update = review_agent.run(bundle)
        bundle.critic_findings = findings
        bundle.evidence_update = evidence_update
        bundles.append(bundle)
        feedback_records.append(build_experimental_feedback(bundle))
        _log(verbose, f"plan {idx}/{len(plans)} reviewed status={evidence_update.get('review_status')}")

    experiment_results_path = Path(paths.get("experiment_results", output_dir / "experiment_results.json"))
    feedback_path = Path(paths.get("experimental_feedback", "outputs/hypotheses/experimental_feedback.json"))
    report_path = Path(paths.get("experiment_report", "reports/phase3_experiment_report.md"))
    write_json(experiment_results_path, [bundle.model_dump() for bundle in bundles])
    write_json(feedback_path, feedback_records)
    _write_report(report_path, bundles, feedback_records)
    _log(verbose, f"outputs results={experiment_results_path} feedback={feedback_path} report={report_path}")
    return {
        "plans": len(plans),
        "results": str(experiment_results_path),
        "experimental_feedback": str(feedback_path),
        "report": str(report_path),
    }


def _write_report(path: Path, bundles: list[ExperimentResultBundle], feedback: list[dict[str, Any]]) -> None:
    lines = ["# Experiment Report", ""]
    for bundle, record in zip(bundles, feedback):
        lines.extend(
            [
                f"## {bundle.plan.hypothesis_title}",
                f"- hypothesis_id: `{bundle.plan.hypothesis_id}`",
                f"- plan_id: `{bundle.plan.plan_id}`",
                f"- predictors: {', '.join(bundle.plan.predictors)}",
                f"- outcomes: {', '.join(bundle.plan.outcomes)}",
                f"- review_status: {record.get('support')}",
                f"- computed_reward: {record.get('computed_reward')}",
                "",
            ]
        )
        if bundle.stats_result:
            lines.append(bundle.stats_result.summary)
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _log(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[experiment] {message}", flush=True)


if __name__ == "__main__":
    print(run_experiment_pipeline())
