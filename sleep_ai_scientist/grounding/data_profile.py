from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import config_path, existing_or_fixture
from sleep_ai_scientist.common.io import read_csv, read_yaml, write_yaml
from sleep_ai_scientist.schemas.data_profile import DataProfile, FeatureProfile
from sleep_ai_scientist.schemas.evidence import EvidenceRecord


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "approved"}


def _approved_set(path: Path) -> set[str]:
    payload = read_yaml(path) if path.exists() else {}
    values = payload.get("approved_variables", payload if isinstance(payload, list) else [])
    return {str(item) for item in values}


def _missing_stats(master_rows: list[dict[str, str]], column: str) -> tuple[float | None, int | None]:
    """Compute availability from the foundation master table without modifying it."""
    if not master_rows or column not in master_rows[0]:
        return None, None
    total = len(master_rows)
    available = sum(1 for row in master_rows if str(row.get(column, "")).strip() not in {"", "NA", "nan", "None"})
    return round(1 - available / total, 3), available


def build_observed_profile(config: dict[str, Any]) -> DataProfile:
    """Build observed_profile from foundation registry/master table or toy fixtures."""
    registry_path = existing_or_fixture(config, "feature_registry", "fixture_feature_registry")
    approved_path = existing_or_fixture(config, "approved_variables", "fixture_approved_variables")
    master_path = existing_or_fixture(config, "multimodal_master_table", "fixture_multimodal_master_table")
    registry = read_csv(registry_path)
    master_rows = read_csv(master_path) if master_path.exists() else []
    approved = _approved_set(approved_path)
    features = []
    for row in registry:
        column = row.get("source_column") or row.get("feature_name") or ""
        missing_rate, n_available = _missing_stats(master_rows, column)
        feature_name = row.get("feature_name", "")
        # Feature metadata comes from the registry; missingness is measured from
        # the master table when available. No new feature names are synthesized.
        features.append(
            FeatureProfile(
                feature_name=feature_name,
                modality=row.get("modality", ""),
                source_file=row.get("source_file", str(master_path.name)),
                source_column=column,
                missing_rate=missing_rate,
                n_available=n_available,
                qc_status=row.get("qc_status", "pass"),
                approved=_truthy(row.get("approved")) or feature_name in approved,
                role=row.get("role", "feature"),
            )
        )
    return DataProfile(profile_type="observed_profile", features=features)


def build_theoretical_profile(evidence: list[EvidenceRecord]) -> DataProfile:
    """Build theoretical variable needs from literature-derived evidence."""
    seen: set[str] = set()
    features = []
    for item in evidence:
        name = item.variable_or_feature or item.mechanism
        if name and name not in seen:
            seen.add(name)
            features.append(
                FeatureProfile(
                    feature_name=name,
                    modality=item.modality,
                    source_file="literature_grounding",
                    source_column=name,
                    role="feature",
                    approved=False,
                )
            )
    return DataProfile(profile_type="theoretical_profile", features=features)


def build_analysis_ready_profile(config: dict[str, Any], observed: DataProfile) -> DataProfile:
    """Filter observed variables by approval, missingness, sample size, and QC."""
    profile_cfg = config.get("data_profile", {})
    max_missing = float(profile_cfg.get("max_missing_rate", 0.4))
    min_n = int(profile_cfg.get("min_n_available", 1))
    accepted_qc = {str(item).lower() for item in profile_cfg.get("accepted_qc_status", ["pass", "usable"])}
    features = [
        item
        for item in observed.features
        if item.approved
        and (item.missing_rate is None or item.missing_rate <= max_missing)
        and (item.n_available is None or item.n_available >= min_n)
        and (not item.qc_status or item.qc_status.lower() in accepted_qc)
    ]
    return DataProfile(profile_type="analysis_ready_profile", features=features)


def write_profiles(config: dict[str, Any], theoretical: DataProfile, observed: DataProfile, analysis_ready: DataProfile) -> None:
    """Persist the three Phase 1 profiles for Phase 2 consumption."""
    out_dir = config_path(config, "output_profiles_dir")
    write_yaml(out_dir / "theoretical_profile.yaml", theoretical.model_dump(mode="json"))
    write_yaml(out_dir / "observed_profile.yaml", observed.model_dump(mode="json"))
    write_yaml(out_dir / "analysis_ready_profile.yaml", analysis_ready.model_dump(mode="json"))
