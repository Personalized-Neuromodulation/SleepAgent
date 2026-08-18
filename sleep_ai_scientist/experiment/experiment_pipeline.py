from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml, write_json
from sleep_ai_scientist.experiment.design_constraints import build_experiment_design_constraints, plan_signature
from sleep_ai_scientist.data_processing.fmri_local_split import run_fmri_local_split
from sleep_ai_scientist.experiment.agents.experiment_design_agent import ExperimentDesignAgent
from sleep_ai_scientist.experiment.agents.feedback_builder import build_experimental_feedback
from sleep_ai_scientist.experiment.agents.planning import load_data_profile
from sleep_ai_scientist.experiment.agents.result_review_agent import ResultReviewAgent
from sleep_ai_scientist.experiment.agents.statistical_model_agent import StatisticalModelAgent
from sleep_ai_scientist.experiment.agents.variable_mapping_agent import VariableMappingAgent
from sleep_ai_scientist.experiment.visualization import render_experiment_visualizations
from sleep_ai_scientist.feature_extraction.feature_pipeline import run_feature_extraction
from sleep_ai_scientist.feature_extraction.profile_builder import TestabilityPrecheck
from sleep_ai_scientist.llm.client import select_llm_profile
from sleep_ai_scientist.schemas.experiment import ExperimentPlan, ExperimentResultBundle


def run_experiment_pipeline(config_path_value: str | Path = "configs/experiment_config.yaml") -> dict[str, Any]:
    config_path = Path(config_path_value)
    config = read_yaml(config_path)
    experiment_config = config.get("experiment", {})
    experiment_config = _with_shared_llm_config(config, experiment_config)
    paths = config.get("paths", {})
    verbose = bool(experiment_config.get("verbose", True))

    output_dir = Path(paths.get("experiment_output_dir", "outputs/experiments"))
    trace_dir = output_dir / "agent_traces"
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir.mkdir(parents=True, exist_ok=True)

    _log(verbose, f"start config={config_path}")
    data_profile_path = Path(paths.get("data_profile", paths.get("design_data_profile", "outputs/profiles/analysis_ready_profile.yaml")))
    extracted_feature_tables: list[dict[str, Any]] = []
    feature_profile_paths: list[str] = []
    merged_feature_paths: list[str] = []
    pre_experiment_features = None
    if bool(config.get("feature_extraction", {}).get("enabled", False)) and not bool(config.get("data_processing", {}).get("enabled", False)):
        pre_plan = _pre_experiment_feature_plan()
        _log(verbose, f"pre-experiment feature extraction plan_id={pre_plan.plan_id}")
        pre_experiment_features = run_feature_extraction(config.get("feature_extraction", {}), pre_plan)
        extracted_feature_tables.extend([table.model_dump(mode="json") for table in pre_experiment_features.tables])
        if pre_experiment_features.profile_path:
            feature_profile_paths.append(pre_experiment_features.profile_path)
            data_profile_path = Path(pre_experiment_features.profile_path)
        if pre_experiment_features.merged_features_path:
            merged_feature_paths.append(pre_experiment_features.merged_features_path)
        _log(
            verbose,
            f"PreExperimentFeatureExtraction done tables={len(pre_experiment_features.tables)} profile={data_profile_path}",
        )
    data_profile = load_data_profile(data_profile_path)
    _log(verbose, f"loaded data_profile={data_profile_path} features={len(data_profile.features)}")
    design_constraints = build_experiment_design_constraints(
        previous_result_paths=_path_list(paths.get("previous_experiment_results")),
        previous_feedback_paths=_path_list(paths.get("previous_experimental_feedback")),
    )
    if design_constraints.get("avoid_signatures") or design_constraints.get("negative_control_failed_predictors"):
        _log(
            verbose,
            "[experiment:constraints] "
            f"previous_results={len(_path_list(paths.get('previous_experiment_results')))} "
            f"tried_signatures={len(design_constraints.get('avoid_signatures', []))} "
            f"negative_failed_predictors={len(design_constraints.get('negative_control_failed_predictors', []))}",
        )

    design_agent = ExperimentDesignAgent(_agent_config(experiment_config, "experiment_design"), output_dir=trace_dir)
    plans = design_agent.run(
        hypothesis_pool_path=paths.get("hypothesis_pool", "outputs/hypotheses/hypothesis_pool.json"),
        data_profile_path=data_profile_path,
        approved_variables_path=paths.get("approved_variables"),
        variable_mapping_path=paths.get("variable_mapping"),
        top_k=int(experiment_config.get("top_k_hypotheses", 1)),
        design_constraints=design_constraints,
    )
    _log(verbose, f"ExperimentDesignAgent done plans={len(plans)}")

    mapping_agent = VariableMappingAgent(experiment_config, output_dir=trace_dir)
    statistical_agent = StatisticalModelAgent(_agent_config(experiment_config, "experiment_statistical_model"), output_dir=trace_dir)
    review_agent = ResultReviewAgent(_agent_config(experiment_config, "experiment_result_review"), output_dir=trace_dir)

    bundles: list[ExperimentResultBundle] = []
    feedback_records: list[dict[str, Any]] = []
    skipped_plans: list[dict[str, Any]] = []
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
        if bool(config.get("feature_extraction", {}).get("enabled", False)) and pre_experiment_features is None:
            _log(verbose, f"plan {idx}/{len(plans)} feature extraction plan_id={plan.plan_id}")
            feature_result = run_feature_extraction(config.get("feature_extraction", {}), plan)
            extracted_feature_tables.extend([table.model_dump(mode="json") for table in feature_result.tables])
            if feature_result.profile_path:
                feature_profile_paths.append(feature_result.profile_path)
            if feature_result.merged_features_path:
                merged_feature_paths.append(feature_result.merged_features_path)
            data_profile = load_data_profile(feature_result.profile_path)
            plan = TestabilityPrecheck().run(plan, data_profile)
            _log(
                verbose,
                f"FeatureExtraction done tables={len(feature_result.tables)} profile_features={len(data_profile.features)}",
            )
        elif pre_experiment_features is not None:
            plan = TestabilityPrecheck().run(plan, data_profile)
        _log(verbose, f"plan {idx}/{len(plans)} mapping plan_id={plan.plan_id}")
        mapped_plan = mapping_agent.run(plan, data_profile)
        signature = plan_signature(mapped_plan)
        if signature in set(design_constraints.get("avoid_signatures", [])):
            skipped = {
                "plan_id": mapped_plan.plan_id,
                "hypothesis_id": mapped_plan.hypothesis_id,
                "reason": "duplicate_experiment_signature",
                "signature": signature,
                "stage": "post_mapping_pre_statistics",
                "predictors": list(mapped_plan.predictors),
                "outcomes": list(mapped_plan.outcomes),
                "covariates": list(mapped_plan.covariates),
            }
            skipped_plans.append(skipped)
            _log(verbose, f"plan {idx}/{len(plans)} skipped duplicate_signature={signature}")
            continue
        _log(verbose, f"plan {idx}/{len(plans)} statistics tests={len(mapped_plan.primary_tests)}")
        stats_result, ml_result, robustness, negative_controls, model_trace = statistical_agent.run(
            mapped_plan,
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
    group_specific_outputs = _write_group_specific_model_outputs(experiment_results_path.parent, bundles)
    write_json(trace_dir / "experiment_pipeline.skipped_plans.json", skipped_plans)
    _write_report(report_path, bundles, feedback_records)
    visualization_dir = Path(paths.get("experiment_visualizations", experiment_results_path.parent / "visuals"))
    visualizations = render_experiment_visualizations(bundles, visualization_dir, skipped_plans=skipped_plans)
    _log(verbose, f"outputs results={experiment_results_path} feedback={feedback_path} report={report_path} visualizations={visualizations.get('html')}")
    return {
        "plans": len(plans),
        "executed_plans": len(bundles),
        "skipped_plans": skipped_plans,
        "results": str(experiment_results_path),
        "experimental_feedback": str(feedback_path),
        "report": str(report_path),
        "visualizations": visualizations,
        "group_specific_models": group_specific_outputs,
        "feature_tables": extracted_feature_tables,
        "feature_profiles": feature_profile_paths,
        "merged_feature_tables": merged_feature_paths,
    }


def _write_group_specific_model_outputs(output_dir: Path, bundles: list[ExperimentResultBundle]) -> dict[str, str]:
    records = _group_specific_model_records(bundles)
    csv_path = output_dir / "group_specific_model_results.csv"
    json_path = output_dir / "group_specific_model_results.json"
    frame = pd.DataFrame(records)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv_path, index=False)
    write_json(json_path, records)
    return {"csv": str(csv_path), "json": str(json_path)}


def _group_specific_model_records(bundles: list[ExperimentResultBundle]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for bundle in bundles:
        tests = bundle.stats_result.tests if bundle.stats_result else []
        for test in tests:
            context = test.metadata.get("clinical_group_context", {}) if isinstance(test.metadata, dict) else {}
            models = context.get("group_specific_models") or {}
            healthy = models.get("healthy") or {}
            nonhealthy = models.get("nonhealthy") or {}
            interaction = models.get("interaction") or {}
            records.append(
                {
                    "plan_id": bundle.plan.plan_id,
                    "hypothesis_id": bundle.plan.hypothesis_id,
                    "test_id": test.test_id,
                    "predictor": test.predictor,
                    "outcome": test.outcome,
                    "healthy_n": healthy.get("n"),
                    "healthy_slope": healthy.get("slope"),
                    "healthy_p_value": healthy.get("p_value"),
                    "healthy_r_squared": healthy.get("r_squared"),
                    "nonhealthy_n": nonhealthy.get("n"),
                    "nonhealthy_slope": nonhealthy.get("slope"),
                    "nonhealthy_p_value": nonhealthy.get("p_value"),
                    "nonhealthy_r_squared": nonhealthy.get("r_squared"),
                    "interaction_n": interaction.get("n"),
                    "interaction_slope_difference_healthy_minus_nonhealthy": interaction.get(
                        "slope_difference_healthy_minus_nonhealthy"
                    ),
                    "interaction_p_value": interaction.get("p_value"),
                    "interaction_r_squared": interaction.get("r_squared"),
                    "interaction_interpretation": interaction.get("interpretation"),
                }
            )
    return records


def _with_shared_llm_config(config: dict[str, Any], experiment_config: dict[str, Any]) -> dict[str, Any]:
    paths = config.get("paths", {})
    llm_config_path = paths.get("llm_config")
    if not llm_config_path:
        return experiment_config
    path = resolve_path(llm_config_path)
    if not path.exists():
        return experiment_config
    shared = read_yaml(path)
    merged = dict(experiment_config)
    for key in ("llm_provider", "online_llm", "ollama", "llm", "llm_profiles", "llm_tasks"):
        if key in shared:
            merged[key] = shared[key]
    if "llm" not in merged:
        merged["llm"] = select_llm_profile(merged, "experiment", log_prefix="experiment")
    return merged


def _pre_experiment_feature_plan() -> ExperimentPlan:
    return ExperimentPlan(
        plan_id="pre_experiment_features",
        hypothesis_id="pre_experiment_features",
        hypothesis_title="Pre-experiment feature extraction",
        scientific_question="Build analysis-ready multimodal features before experiment design.",
    )


def _agent_config(experiment_config: dict[str, Any], task_name: str) -> dict[str, Any]:
    selected = select_llm_profile(experiment_config, task_name, log_prefix="experiment")
    merged = dict(experiment_config)
    merged["llm"] = selected
    return merged


def _path_list(value: Any) -> list[Path]:
    if not value:
        return []
    if isinstance(value, list):
        return [Path(item) for item in value if str(item).strip()]
    return [Path(value)]


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
