from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_csv, read_yaml
from sleep_ai_scientist.schemas.hypothesis import EvidenceLevel, HypothesisRecord, HypothesisStatus, HypothesisVariables


def _features(profile_path: Path) -> dict[str, dict[str, Any]]:
    profile = read_yaml(profile_path) if profile_path.exists() else {"features": []}
    return {item["feature_name"]: item for item in profile.get("features", []) if item.get("feature_name")}


def _evidence_by_mechanism(evidence_rows: list[dict[str, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for row in evidence_rows:
        mechanism = row.get("mechanism", "")
        evidence_id = row.get("evidence_id", "")
        if mechanism and evidence_id and evidence_id not in grouped.setdefault(mechanism, []):
            grouped[mechanism].append(evidence_id)
    return grouped


def _modalities(variables: list[str], features: dict[str, dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for variable in variables:
        modality = features.get(variable, {}).get("modality")
        if modality and modality not in values:
            values.append(modality)
    return values


def _covariates(features: dict[str, dict[str, Any]], candidates: list[str]) -> list[str]:
    return [name for name in candidates if name in features]


def _make(
    hypothesis_id: str,
    title: str,
    mechanism: str,
    independent: list[str],
    dependent: list[str],
    covariates: list[str],
    prediction: str,
    model: str,
    direction: dict[str, str],
    features: dict[str, dict[str, Any]],
    evidence_ids: list[str],
) -> HypothesisRecord:
    used = independent + dependent + covariates
    return HypothesisRecord(
        hypothesis_id=hypothesis_id,
        title=title,
        mechanism=mechanism,
        primary_prediction=prediction,
        secondary_predictions=[],
        variables=HypothesisVariables(independent=independent, dependent=dependent, covariates=covariates),
        required_modalities=_modalities(used, features),
        analysis_models=[model],
        expected_direction=direction,
        falsification_criteria=[
            "Primary predictor has no association with the outcome after prespecified covariate adjustment.",
            "Corrected p-value and effect-size direction do not support the primary prediction.",
        ],
        risk_flags=[],
        evidence_level=EvidenceLevel.exploratory,
        status=HypothesisStatus.generated,
        supporting_evidence_ids=evidence_ids,
        used_data_features=used,
    )


def generate_candidate_hypotheses(config: dict[str, Any]) -> list[HypothesisRecord]:
    """Generate deterministic scientific-loop hypotheses from grounded, analysis-ready variables."""
    root = Path(config["_project_root"])
    inputs = config.get("inputs", {})
    evidence_path = resolve_path(inputs.get("evidence_table", "outputs/grounding/evidence_table.csv"), root)
    profile_path = resolve_path(inputs.get("analysis_ready_profile", "outputs/profiles/analysis_ready_profile.yaml"), root)
    evidence_rows = read_csv(evidence_path) if evidence_path.exists() else []
    features = _features(profile_path)
    evidence = _evidence_by_mechanism(evidence_rows)
    cov_common = _covariates(features, ["age", "sex", "medication"])
    cov_motion = _covariates(features, ["age", "sex", "mean_FD", "in_scanner_sleep_time", "medication"])
    specs = [
        ("INS vs HC slow-wave density difference", "slow-wave generation", ["group"], ["slow_wave_density"], cov_common, "slow_wave_density differs between insomnia and healthy control groups.", "group_difference", {"group": "INS lower than HC"}),
        ("INS vs HC beta power difference", "hyperarousal", ["group"], ["beta_power"], cov_common, "beta_power differs between insomnia and healthy control groups.", "group_difference", {"group": "INS higher than HC"}),
        ("Slow-wave density association with insomnia severity", "slow-wave generation", ["slow_wave_density"], ["ISI"], cov_common, "Lower slow_wave_density is associated with higher ISI.", "symptom_association", {"slow_wave_density": "negative"}),
        ("Spindle density association with thalamocortical coupling", "thalamocortical coupling", ["spindle_density"], ["thalamus_DMN_FC"], cov_motion, "spindle_density is associated with thalamus_DMN_FC.", "cross_modal_bridge", {"spindle_density": "positive"}),
        ("Thalamic radiation FA association with slow-wave density", "white matter integrity", ["thalamic_radiation_FA"], ["slow_wave_density"], cov_common, "Higher thalamic_radiation_FA is associated with higher slow_wave_density.", "cross_modal_bridge", {"thalamic_radiation_FA": "positive"}),
        ("Thalamus-DMN connectivity association with insomnia severity", "thalamocortical coupling", ["thalamus_DMN_FC"], ["ISI"], cov_motion, "thalamus_DMN_FC is associated with ISI after motion and sleep covariate adjustment.", "symptom_association", {"thalamus_DMN_FC": "positive"}),
        ("Multimodal neural model predicting insomnia severity", "multimodal sleep disruption", ["slow_wave_density", "thalamus_DMN_FC", "thalamic_radiation_FA"], ["ISI"], cov_motion, "EEG, fMRI, and DTI features jointly predict ISI.", "multimodal_prediction", {"slow_wave_density": "negative", "thalamus_DMN_FC": "positive", "thalamic_radiation_FA": "negative"}),
    ]
    hypotheses: list[HypothesisRecord] = []
    max_h = int(config.get("generation", {}).get("max_hypotheses", 30))
    for index, spec in enumerate(specs, start=1):
        title, mechanism, independent, dependent, covariates, prediction, model, direction = spec
        missing = [name for name in independent + dependent if name != "group" and name not in features]
        if missing and config.get("generation", {}).get("require_existing_variables", True):
            continue
        hypotheses.append(_make(f"H{index:03d}", title, mechanism, independent, dependent, covariates, prediction, model, direction, features, evidence.get(mechanism, [])))
        if len(hypotheses) >= max_h:
            break
    return hypotheses
