from __future__ import annotations

import html as html_lib
import json
import math
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_cache")
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["NUMBA_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sleep_ai_scientist.common.io import write_json


DEFAULT_HEALTHY_PREFIX = "sub-YZHC"
DEFAULT_NETWORK_COORDS = {
    "thalamus": (0.0, -18.0, 8.0),
    "DMN": (0.0, -52.0, 28.0),
    "salience": (0.0, 18.0, 8.0),
    "frontoparietal": (0.0, 42.0, 30.0),
}


def run_grounding_locked_validation(
    master_table: str | Path,
    hypothesis_spec: str | Path,
    *,
    output_dir: str | Path = "outputs/group_contrast/grounding_candidate_fc",
    healthy_prefix: str = DEFAULT_HEALTHY_PREFIX,
    make_plots: bool = True,
) -> dict[str, Any]:
    """Analyze grounding-prespecified ROI-FC hypotheses with local group contrasts.

    The local table is deliberately used only after the hypothesis spec has
    selected candidate FC variables. This keeps the workflow confirmatory while
    testing healthy/nonhealthy group differences, nonhealthy FC-symptom links,
    healthy controls, and group-by-FC interactions.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    spec = _load_grounding_spec(hypothesis_spec)
    candidate_fc = [str(item) for item in spec.get("candidate_fc", []) if str(item)]
    if not candidate_fc:
        raise ValueError("Grounding hypothesis spec must define non-empty candidate_fc.")

    frame = pd.read_csv(master_table)
    clinical_anchors = _ordered_unique([str(item) for item in spec.get("clinical_anchors", []) if str(item)] + ["ISI", "PSQI"])
    subject_table = build_subject_level_validation_table(
        frame,
        candidate_fc,
        healthy_prefix=healthy_prefix,
        clinical_anchors=clinical_anchors,
    )
    stats_table = compute_group_feature_stats(subject_table, candidate_fc)
    available_anchors = [anchor for anchor in clinical_anchors if anchor in subject_table.columns]
    symptom_stats = compute_group_symptom_association_stats(subject_table, candidate_fc, available_anchors)

    subject_path = output / "subject_level_validation_table.csv"
    stats_path = output / "feature_stats.csv"
    symptom_stats_path = output / "group_symptom_stats.csv"
    node_coords_path = output / "node_coordinates.csv"
    metrics_path = output / "metrics.json"
    support_path = output / "hypothesis_support.json"
    support_report_path = output / "hypothesis_support.md"
    subject_table.to_csv(subject_path, index=False)
    stats_table.to_csv(stats_path, index=False)
    symptom_stats.to_csv(symptom_stats_path, index=False)
    node_coordinates = build_node_coordinate_table(subject_table, _networks_from_rows(stats_table))
    node_coordinates.to_csv(node_coords_path, index=False)

    figures: list[str] = []
    visualizations: list[dict[str, str]] = []
    if make_plots:
        figures_dir = output / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        visualizations = plot_grounding_validation_connections(
            stats_table,
            figures_dir,
            node_coordinates=node_coordinates,
            symptom_stats=symptom_stats,
        )
        figures.extend(item["path"] for item in visualizations)

    support = summarize_grounding_hypothesis_support(stats_table, symptom_stats, spec)
    write_json(support_path, support)
    support_report_path.write_text(_support_markdown(support), encoding="utf-8")

    payload = {
        "subject_table": str(subject_path),
        "feature_stats": str(stats_path),
        "group_symptom_stats": str(symptom_stats_path),
        "node_coordinates": str(node_coords_path),
        "metrics": str(metrics_path),
        "hypothesis_support_path": str(support_path),
        "hypothesis_support_report": str(support_report_path),
        "figures": figures,
        "connection_visualizations": visualizations,
        "metadata": {
            "source": spec.get("source"),
            "hypothesis_id": spec.get("hypothesis_id", ""),
            "hypothesis": spec.get("hypothesis", ""),
            "candidate_fc": candidate_fc,
            "clinical_anchors": clinical_anchors,
            "analyzed_clinical_anchors": available_anchors,
            "healthy_prefix": healthy_prefix,
            "n_subjects": int(subject_table["subject"].nunique()) if "subject" in subject_table.columns else int(len(subject_table)),
            "n_samples": int(len(subject_table)),
            "n_healthy": int(subject_table["healthy_label"].sum()) if not subject_table.empty else 0,
            "n_nonhealthy": int((subject_table["healthy_label"] == 0).sum()) if not subject_table.empty else 0,
            "n_healthy_subjects": int(subject_table.loc[subject_table["healthy_label"] == 1, "subject"].nunique()) if "subject" in subject_table.columns else 0,
            "n_nonhealthy_subjects": int(subject_table.loc[subject_table["healthy_label"] == 0, "subject"].nunique()) if "subject" in subject_table.columns else 0,
            "analysis_unit": "session_sample",
            "analysis_task": "locked_candidate_fc_group_contrast",
            "feature_selection_policy": "grounding_prespecified_only",
        },
        "statistical_model": {
            "status": "run",
            "task": "locked_candidate_fc_group_contrast",
            "feature_selection_policy": "grounding_prespecified_only",
            "group_contrast": str(stats_path),
            "symptom_association": str(symptom_stats_path),
            "tested_groups": ["healthy", "nonhealthy"],
            "interaction_model": "clinical_anchor ~ FC + healthy_label + FC:healthy_label",
        },
        "hypothesis_support": support,
    }
    write_json(metrics_path, payload)
    return payload


def run_locked_candidate_fc_group_contrast(
    master_table: str | Path,
    hypothesis_spec: str | Path,
    *,
    output_dir: str | Path = "outputs/group_contrast/grounding_candidate_fc",
    healthy_prefix: str = DEFAULT_HEALTHY_PREFIX,
    make_plots: bool = True,
) -> dict[str, Any]:
    return run_grounding_locked_validation(
        master_table,
        hypothesis_spec,
        output_dir=output_dir,
        healthy_prefix=healthy_prefix,
        make_plots=make_plots,
    )


def build_subject_level_validation_table(
    frame: pd.DataFrame,
    candidate_fc: list[str],
    *,
    healthy_prefix: str = DEFAULT_HEALTHY_PREFIX,
    clinical_anchors: list[str] | None = None,
) -> pd.DataFrame:
    sample_col = _sample_column(frame)
    subject_col = _subject_column(frame)
    fc_sources = _resolve_feature_columns(frame, candidate_fc, prefix="fmri_")
    missing = [column for column in candidate_fc if column not in fc_sources]
    if missing:
        raise ValueError(f"Grounding candidate_fc columns are missing from master table: {missing}")
    clean = frame.copy()
    roi_status_col = _first_existing(clean, ["roi_fc_status", "fmri_roi_fc_status"])
    if roi_status_col:
        clean = clean[clean[roi_status_col].astype(str).str.lower().eq("computed")]
    has_fmri_col = _first_existing(clean, ["has_fMRI", "fmri_has_fMRI"])
    if has_fmri_col:
        clean = clean[clean[has_fmri_col].map(_as_bool)]
    clean["sample_id"] = clean[sample_col].map(str)
    clean["subject"] = clean[subject_col].map(_normalize_subject)
    clean["healthy_label"] = clean["subject"].str.startswith(healthy_prefix).astype(int)
    for feature, source_column in fc_sources.items():
        if feature not in clean.columns:
            clean[feature] = clean[source_column]
    anchor_sources = _resolve_feature_columns(clean, clinical_anchors or [], prefix="scales_")
    for anchor, source_column in anchor_sources.items():
        if anchor not in clean.columns:
            clean[anchor] = clean[source_column]
    anchors = list(anchor_sources)
    covariates = _available_covariates(clean)
    coord_numeric = _coordinate_numeric_columns(clean)
    coord_metadata = [column for column in ("roi_coord_source", "fmri_roi_coord_source", "roi_coord_space", "fmri_roi_coord_space") if column in clean.columns]
    numeric_columns = [*candidate_fc, *covariates, *anchors, *coord_numeric]
    keep = ["sample_id", "subject", "healthy_label", *candidate_fc, *covariates, *anchors, *coord_numeric, *coord_metadata]
    clean = clean[keep].copy()
    for column in numeric_columns:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    ordered = ["sample_id", "subject", "healthy_label", *candidate_fc, *_available_covariates(clean), *anchors, *coord_numeric, *coord_metadata]
    return clean[ordered].sort_values(["subject", "sample_id"]).reset_index(drop=True)


def build_node_coordinate_table(subject_table: pd.DataFrame, networks: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for network in networks:
        x_col, y_col, z_col = f"{network}_coord_x", f"{network}_coord_y", f"{network}_coord_z"
        has_atlas_coords = all(column in subject_table.columns for column in (x_col, y_col, z_col))
        if has_atlas_coords:
            x = pd.to_numeric(subject_table[x_col], errors="coerce").median()
            y = pd.to_numeric(subject_table[y_col], errors="coerce").median()
            z = pd.to_numeric(subject_table[z_col], errors="coerce").median()
        else:
            x = y = z = math.nan
        if all(pd.notna(value) for value in (x, y, z)):
            coord_source = _coordinate_source_summary(subject_table)
            coord_space = _metadata_mode(subject_table, ["roi_coord_space", "fmri_roi_coord_space"], "atlas_image_world")
            status = "atlas_derived"
        else:
            x, y, z = DEFAULT_NETWORK_COORDS.get(network, (0.0, 0.0, 0.0))
            coord_source = "schematic fallback coordinates"
            coord_space = "approximate_MNI"
            status = "schematic_fallback"
        rows.append(
            {
                "network": network,
                "x": float(x),
                "y": float(y),
                "z": float(z),
                "n_subjects": int(len(subject_table)),
                "coord_source": coord_source,
                "coord_space": coord_space,
                "coord_status": status,
            }
        )
    return pd.DataFrame(rows)


def compute_group_feature_stats(subject_table: pd.DataFrame, candidate_fc: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for feature in candidate_fc:
        healthy = pd.to_numeric(subject_table.loc[subject_table["healthy_label"] == 1, feature], errors="coerce").dropna()
        nonhealthy = pd.to_numeric(subject_table.loc[subject_table["healthy_label"] == 0, feature], errors="coerce").dropna()
        h_mean = float(healthy.mean()) if len(healthy) else math.nan
        n_mean = float(nonhealthy.mean()) if len(nonhealthy) else math.nan
        diff = n_mean - h_mean if math.isfinite(h_mean) and math.isfinite(n_mean) else math.nan
        p_value = _welch_p_value(healthy, nonhealthy)
        rows.append(
            {
                "feature": feature,
                "network_a": _feature_networks(feature)[0],
                "network_b": _feature_networks(feature)[1],
                "healthy_mean": h_mean,
                "nonhealthy_mean": n_mean,
                "nonhealthy_minus_healthy": diff,
                "welch_p": p_value,
                "n_healthy": int(len(healthy)),
                "n_nonhealthy": int(len(nonhealthy)),
            }
        )
    result = pd.DataFrame(rows)
    result["fdr_q"] = _benjamini_hochberg(result["welch_p"].tolist()) if not result.empty else []
    result["significant_fdr_0_05"] = result["fdr_q"].le(0.05)
    return result


def compute_group_symptom_association_stats(
    subject_table: pd.DataFrame,
    candidate_fc: list[str],
    clinical_anchors: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for anchor in clinical_anchors:
        if anchor not in subject_table.columns:
            continue
        for feature in candidate_fc:
            if feature not in subject_table.columns:
                continue
            healthy = subject_table[subject_table["healthy_label"] == 1]
            nonhealthy = subject_table[subject_table["healthy_label"] == 0]
            healthy_r, healthy_p, healthy_n = _spearman_pair(healthy[feature], healthy[anchor])
            nonhealthy_r, nonhealthy_p, nonhealthy_n = _spearman_pair(nonhealthy[feature], nonhealthy[anchor])
            interaction = _group_fc_interaction(subject_table, feature, anchor)
            rows.append(
                {
                    "clinical_anchor": anchor,
                    "feature": feature,
                    "network_a": _feature_networks(feature)[0],
                    "network_b": _feature_networks(feature)[1],
                    "healthy_spearman_r": healthy_r,
                    "healthy_spearman_p": healthy_p,
                    "healthy_n": healthy_n,
                    "nonhealthy_spearman_r": nonhealthy_r,
                    "nonhealthy_spearman_p": nonhealthy_p,
                    "nonhealthy_n": nonhealthy_n,
                    "group_fc_interaction_beta": interaction["beta"],
                    "group_fc_interaction_p": interaction["p_value"],
                    "group_fc_interaction_n": interaction["n"],
                    "nonhealthy_mechanism_direction": _observed_direction(nonhealthy_r),
                    "healthy_control_direction": _observed_direction(healthy_r),
                }
            )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["nonhealthy_spearman_fdr_q"] = _benjamini_hochberg(result["nonhealthy_spearman_p"].tolist())
        result["healthy_spearman_fdr_q"] = _benjamini_hochberg(result["healthy_spearman_p"].tolist())
        result["group_fc_interaction_fdr_q"] = _benjamini_hochberg(result["group_fc_interaction_p"].tolist())
    return result


def fit_grounding_locked_classifier(subject_table: pd.DataFrame, candidate_fc: list[str]) -> dict[str, Any]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, confusion_matrix, roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    clean = subject_table[["healthy_label", *candidate_fc]].copy()
    for column in candidate_fc:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna(subset=["healthy_label", *candidate_fc])
    if clean.empty or clean["healthy_label"].nunique() < 2:
        return {
            "status": "not_run",
            "reason": "Insufficient classes after cleaning.",
            "model": "logistic_regression",
            "task": "healthy_vs_nonhealthy",
            "positive_class": "healthy",
            "features": candidate_fc,
        }
    y = clean["healthy_label"].astype(int)
    min_class_count = int(y.value_counts().min())
    if len(clean) < 4 or min_class_count < 2:
        return {
            "status": "not_run",
            "reason": "Insufficient subjects per class for stratified CV.",
            "model": "logistic_regression",
            "task": "healthy_vs_nonhealthy",
            "positive_class": "healthy",
            "features": candidate_fc,
            "n": int(len(clean)),
        }
    folds = min(5, min_class_count)
    estimator = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, solver="liblinear", random_state=42))
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
    x = clean[candidate_fc]
    predictions = cross_val_predict(estimator, x, y, cv=cv)
    probabilities = cross_val_predict(estimator, x, y, cv=cv, method="predict_proba")[:, 1]
    estimator.fit(x, y)
    logistic = estimator.named_steps["logisticregression"]
    coefficients = {feature: float(value) for feature, value in zip(candidate_fc, logistic.coef_[0], strict=False)}
    return {
        "status": "run",
        "model": "logistic_regression",
        "task": "healthy_vs_nonhealthy",
        "positive_class": "healthy",
        "features": candidate_fc,
        "n": int(len(clean)),
        "cv_folds": int(folds),
        "accuracy": float(accuracy_score(y, predictions)),
        "roc_auc": float(roc_auc_score(y, probabilities)),
        "confusion_matrix": confusion_matrix(y, predictions, labels=[0, 1]).tolist(),
        "coefficients": coefficients,
    }


def plot_grounding_validation_connections(
    stats_table: pd.DataFrame,
    figures_dir: str | Path,
    *,
    node_coordinates: pd.DataFrame | None = None,
    symptom_stats: pd.DataFrame | None = None,
) -> list[dict[str, str]]:
    output = Path(figures_dir)
    output.mkdir(parents=True, exist_ok=True)
    for stale_name in (
        "mean_difference_connections.png",
        "significant_connections.png",
        "classification_weight_connections.png",
        "classification_weight_connectome.png",
        "classification_weight_connectome_3d.html",
    ):
        stale_path = output / stale_name
        if stale_path.exists():
            stale_path.unlink()
    paths = [
        _plot_connection_connectome(
            stats_table,
            value_column="nonhealthy_minus_healthy",
            title="Grounding FC: Non-healthy minus healthy",
            path=output / "mean_difference_connectome.png",
            highlight_column=None,
            kind="mean_difference_connectome",
            node_coordinates=node_coordinates,
        ),
        _plot_connection_connectome_3d(
            stats_table,
            value_column="nonhealthy_minus_healthy",
            title="Grounding FC: Non-healthy minus healthy",
            path=output / "mean_difference_connectome_3d.html",
            highlight_column=None,
            kind="mean_difference_connectome_3d",
            node_coordinates=node_coordinates,
        ),
        _plot_connection_connectome(
            stats_table,
            value_column="nonhealthy_minus_healthy",
            title="Grounding FC: FDR-significant group differences",
            path=output / "significant_connectome.png",
            highlight_column="significant_fdr_0_05",
            kind="significant_connectome",
            node_coordinates=node_coordinates,
        ),
        _plot_connection_connectome_3d(
            stats_table,
            value_column="nonhealthy_minus_healthy",
            title="Grounding FC: FDR-significant group differences",
            path=output / "significant_connectome_3d.html",
            highlight_column="significant_fdr_0_05",
            kind="significant_connectome_3d",
            node_coordinates=node_coordinates,
        ),
    ]
    if symptom_stats is not None and not symptom_stats.empty:
        for anchor in _ordered_unique([str(item) for item in symptom_stats["clinical_anchor"].dropna().tolist()]):
            anchor_rows = symptom_stats[symptom_stats["clinical_anchor"].astype(str) == anchor]
            safe_anchor = _safe_filename(anchor)
            paths.extend(
                [
                    _plot_connection_connectome(
                        anchor_rows,
                        value_column="nonhealthy_spearman_r",
                        title=f"Grounding FC: Non-healthy FC-{anchor} association",
                        path=output / f"nonhealthy_{safe_anchor}_symptom_connectome.png",
                        highlight_column=None,
                        kind=f"nonhealthy_{safe_anchor}_symptom_connectome",
                        node_coordinates=node_coordinates,
                    ),
                    _plot_connection_connectome_3d(
                        anchor_rows,
                        value_column="nonhealthy_spearman_r",
                        title=f"Grounding FC: Non-healthy FC-{anchor} association",
                        path=output / f"nonhealthy_{safe_anchor}_symptom_connectome_3d.html",
                        highlight_column=None,
                        kind=f"nonhealthy_{safe_anchor}_symptom_connectome_3d",
                        node_coordinates=node_coordinates,
                    ),
                    _plot_connection_connectome(
                        anchor_rows,
                        value_column="healthy_spearman_r",
                        title=f"Grounding FC: Healthy-control FC-{anchor} association",
                        path=output / f"healthy_{safe_anchor}_control_symptom_connectome.png",
                        highlight_column=None,
                        kind=f"healthy_{safe_anchor}_control_symptom_connectome",
                        node_coordinates=node_coordinates,
                    ),
                    _plot_connection_connectome_3d(
                        anchor_rows,
                        value_column="healthy_spearman_r",
                        title=f"Grounding FC: Healthy-control FC-{anchor} association",
                        path=output / f"healthy_{safe_anchor}_control_symptom_connectome_3d.html",
                        highlight_column=None,
                        kind=f"healthy_{safe_anchor}_control_symptom_connectome_3d",
                        node_coordinates=node_coordinates,
                    ),
                    _plot_connection_connectome(
                        anchor_rows,
                        value_column="group_fc_interaction_beta",
                        title=f"Grounding FC: Group x FC interaction for {anchor}",
                        path=output / f"group_fc_{safe_anchor}_interaction_connectome.png",
                        highlight_column=None,
                        kind=f"group_fc_{safe_anchor}_interaction_connectome",
                        node_coordinates=node_coordinates,
                    ),
                    _plot_connection_connectome_3d(
                        anchor_rows,
                        value_column="group_fc_interaction_beta",
                        title=f"Grounding FC: Group x FC interaction for {anchor}",
                        path=output / f"group_fc_{safe_anchor}_interaction_connectome_3d.html",
                        highlight_column=None,
                        kind=f"group_fc_{safe_anchor}_interaction_connectome_3d",
                        node_coordinates=node_coordinates,
                    ),
                ]
            )
    return [item for item in paths if Path(item["path"]).exists()]


def summarize_grounding_hypothesis_support(
    stats_table: pd.DataFrame,
    symptom_stats: pd.DataFrame,
    spec: dict[str, Any],
) -> dict[str, Any]:
    expected = spec.get("expected_direction") or {}
    if not isinstance(expected, dict):
        expected = {}
    rows: list[dict[str, Any]] = []
    for _, row in stats_table.iterrows():
        feature = str(row["feature"])
        diff = float(row["nonhealthy_minus_healthy"]) if pd.notna(row["nonhealthy_minus_healthy"]) else None
        direction = _observed_direction(diff)
        expected_direction = str(expected.get(feature, ""))
        direction_matches = _direction_matches(direction, expected_direction) if expected_direction else None
        significant = bool(row.get("significant_fdr_0_05", False))
        supported = bool(significant and (direction_matches is not False))
        rows.append(
            {
                "feature": feature,
                "expected_direction": expected_direction,
                "observed_direction": direction,
                "direction_matches": direction_matches,
                "healthy_mean": _json_float(row.get("healthy_mean")),
                "nonhealthy_mean": _json_float(row.get("nonhealthy_mean")),
                "nonhealthy_minus_healthy": diff,
                "welch_p": _json_float(row.get("welch_p")),
                "fdr_q": _json_float(row.get("fdr_q")),
                "significant_fdr_0_05": significant,
                "supported": supported,
            }
        )
    supported_features = [item["feature"] for item in rows if item["supported"]]
    return {
        "hypothesis_id": str(spec.get("hypothesis_id", "")),
        "hypothesis": str(spec.get("hypothesis", "")),
        "evidence_ids": list(spec.get("evidence_ids", []) or []),
        "candidate_fc": [str(item) for item in spec.get("candidate_fc", []) or []],
        "feature_support": rows,
        "symptom_mechanism_summary": _symptom_mechanism_summary(symptom_stats),
        "supported_features": supported_features,
        "supported_feature_count": len(supported_features),
        "conclusion": _support_conclusion(supported_features, symptom_stats),
    }


def _load_grounding_spec(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    source = str(payload.get("source", "")).strip().lower()
    if source != "grounding":
        raise ValueError("Hypothesis spec must have source='grounding' to avoid local-data-derived hypotheses.")
    return payload


def _subject_column(frame: pd.DataFrame) -> str:
    if "subject" in frame.columns:
        return "subject"
    if "subject_id" in frame.columns:
        return "subject_id"
    raise ValueError("Master table must include subject or subject_id.")


def _sample_column(frame: pd.DataFrame) -> str:
    if "subject_id" in frame.columns:
        return "subject_id"
    if "sample_id" in frame.columns:
        return "sample_id"
    if "subject" in frame.columns:
        return "subject"
    raise ValueError("Master table must include subject_id, sample_id, or subject.")


def _normalize_subject(value: Any) -> str:
    text = str(value)
    for part in text.split("_"):
        if part.startswith("sub-"):
            return part
    return text


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _available_covariates(frame: pd.DataFrame) -> list[str]:
    candidates = ["age", "sex", "mean_FD", "max_FD", "mean_DVARS", "percent_high_motion"]
    return [column for column in candidates if column in frame.columns]


def _resolve_feature_columns(frame: pd.DataFrame, features: list[str], *, prefix: str) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for feature in features:
        if feature in resolved:
            continue
        prefixed = f"{prefix}{feature}"
        if feature in frame.columns:
            resolved[feature] = feature
        elif prefixed in frame.columns:
            resolved[feature] = prefixed
    return resolved


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def _first_existing(frame: pd.DataFrame, columns: list[str]) -> str:
    for column in columns:
        if column in frame.columns:
            return column
    return ""


def _coordinate_numeric_columns(frame: pd.DataFrame) -> list[str]:
    columns: list[str] = []
    for network in DEFAULT_NETWORK_COORDS:
        for axis in ("x", "y", "z"):
            for column in (f"{network}_coord_{axis}", f"fmri_{network}_coord_{axis}"):
                if column in frame.columns:
                    canonical = f"{network}_coord_{axis}"
                    if canonical not in frame.columns and column != canonical:
                        frame[canonical] = frame[column]
                    if canonical in frame.columns and canonical not in columns:
                        columns.append(canonical)
                    break
    return columns


def _first_nonempty(values: pd.Series) -> str:
    for value in values:
        if pd.notna(value) and str(value).strip():
            return str(value)
    return ""


def _metadata_mode(frame: pd.DataFrame, columns: list[str], default: str) -> str:
    values: list[str] = []
    for column in columns:
        if column in frame.columns:
            values.extend(str(value) for value in frame[column].dropna().tolist() if str(value).strip())
    if not values:
        return default
    return str(pd.Series(values).mode().iat[0])


def _coordinate_source_summary(frame: pd.DataFrame) -> str:
    values: list[str] = []
    for column in ("roi_coord_source", "fmri_roi_coord_source"):
        if column in frame.columns:
            values.extend(str(value) for value in frame[column].dropna().tolist() if str(value).strip())
    unique_values = sorted(set(values))
    if not unique_values:
        return "atlas-derived ROI centroid"
    if len(unique_values) == 1:
        return unique_values[0]
    return f"atlas-derived ROI centroid from {len(unique_values)} subject atlas masks"


def _coords_by_network(networks: list[str], node_coordinates: pd.DataFrame | None) -> dict[str, tuple[float, float, float]]:
    if node_coordinates is None or node_coordinates.empty or "network" not in node_coordinates.columns:
        return {network: DEFAULT_NETWORK_COORDS.get(network, (0.0, 0.0, 0.0)) for network in networks}
    indexed = node_coordinates.set_index("network")
    coords: dict[str, tuple[float, float, float]] = {}
    for network in networks:
        if network in indexed.index:
            row = indexed.loc[network]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            values = [pd.to_numeric(row.get(axis), errors="coerce") for axis in ("x", "y", "z")]
            if all(pd.notna(value) for value in values):
                coords[network] = (float(values[0]), float(values[1]), float(values[2]))
                continue
        coords[network] = DEFAULT_NETWORK_COORDS.get(network, (0.0, 0.0, 0.0))
    return coords


def _coordinate_summary(node_coordinates: pd.DataFrame | None) -> tuple[str, str]:
    if node_coordinates is None or node_coordinates.empty:
        return "schematic fallback coordinates", "approximate_MNI"
    return (
        _metadata_mode(node_coordinates, ["coord_source"], "schematic fallback coordinates"),
        _metadata_mode(node_coordinates, ["coord_space"], "approximate_MNI"),
    )


def _observed_direction(diff: float | None) -> str:
    if diff is None or not math.isfinite(float(diff)):
        return "unknown"
    if diff > 0:
        return "nonhealthy_greater"
    if diff < 0:
        return "nonhealthy_lower"
    return "no_difference"


def _direction_matches(observed: str, expected: str) -> bool | None:
    if not expected:
        return None
    normalized = expected.strip().lower()
    aliases = {
        "insomnia_greater": "nonhealthy_greater",
        "patient_greater": "nonhealthy_greater",
        "nonhealthy_higher": "nonhealthy_greater",
        "insomnia_lower": "nonhealthy_lower",
        "patient_lower": "nonhealthy_lower",
        "nonhealthy_less": "nonhealthy_lower",
    }
    normalized = aliases.get(normalized, normalized)
    return observed == normalized


def _json_float(value: Any) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) else None


def _support_conclusion(supported_features: list[str], symptom_stats: pd.DataFrame) -> str:
    if supported_features:
        return "supported_by_group_contrast"
    if not symptom_stats.empty:
        nonhealthy_q = pd.to_numeric(symptom_stats.get("nonhealthy_spearman_fdr_q"), errors="coerce")
        interaction_q = pd.to_numeric(symptom_stats.get("group_fc_interaction_fdr_q"), errors="coerce")
        if bool(nonhealthy_q.le(0.05).any()) or bool(interaction_q.le(0.05).any()):
            return "not_supported_by_fdr_group_difference_but_supported_by_symptom_mechanism"
    return "not_supported_by_available_local_group_contrast"


def _symptom_mechanism_summary(symptom_stats: pd.DataFrame) -> list[dict[str, Any]]:
    if symptom_stats.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in symptom_stats.iterrows():
        nonhealthy_q = _json_float(row.get("nonhealthy_spearman_fdr_q"))
        interaction_q = _json_float(row.get("group_fc_interaction_fdr_q"))
        rows.append(
            {
                "feature": str(row.get("feature", "")),
                "clinical_anchor": str(row.get("clinical_anchor", "")),
                "nonhealthy_spearman_r": _json_float(row.get("nonhealthy_spearman_r")),
                "nonhealthy_spearman_fdr_q": nonhealthy_q,
                "healthy_spearman_r": _json_float(row.get("healthy_spearman_r")),
                "group_fc_interaction_beta": _json_float(row.get("group_fc_interaction_beta")),
                "group_fc_interaction_fdr_q": interaction_q,
                "nonhealthy_symptom_supported": bool(nonhealthy_q is not None and nonhealthy_q <= 0.05),
                "group_interaction_supported": bool(interaction_q is not None and interaction_q <= 0.05),
            }
        )
    return rows


def _support_markdown(support: dict[str, Any]) -> str:
    lines = [
        "# Grounding Hypothesis Support",
        "",
        f"- hypothesis_id: `{support.get('hypothesis_id', '')}`",
        f"- conclusion: `{support.get('conclusion', '')}`",
        f"- supported_feature_count: {support.get('supported_feature_count', 0)}",
        "",
        "## Feature Support",
        "",
        "| feature | expected | observed | FDR q | supported |",
        "|---|---|---|---:|---|",
    ]
    for item in support.get("feature_support", []):
        lines.append(
            "| "
            f"{item.get('feature', '')} | "
            f"{item.get('expected_direction', '')} | "
            f"{item.get('observed_direction', '')} | "
            f"{item.get('fdr_q', '')} | "
            f"{item.get('supported', False)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _welch_p_value(healthy: pd.Series, nonhealthy: pd.Series) -> float | None:
    if len(healthy) < 2 or len(nonhealthy) < 2:
        return None
    _, p_value = stats.ttest_ind(nonhealthy, healthy, equal_var=False, nan_policy="omit")
    return float(p_value) if p_value == p_value else None


def _spearman_pair(x_values: pd.Series, y_values: pd.Series) -> tuple[float | None, float | None, int]:
    clean = pd.DataFrame({"x": pd.to_numeric(x_values, errors="coerce"), "y": pd.to_numeric(y_values, errors="coerce")}).dropna()
    if len(clean) < 3 or clean["x"].nunique() < 2 or clean["y"].nunique() < 2:
        return None, None, int(len(clean))
    rho, p_value = stats.spearmanr(clean["x"], clean["y"], nan_policy="omit")
    rho_value = float(rho) if rho == rho else None
    p_value_clean = float(p_value) if p_value == p_value else None
    return rho_value, p_value_clean, int(len(clean))


def _group_fc_interaction(subject_table: pd.DataFrame, feature: str, anchor: str) -> dict[str, float | int | None]:
    clean = subject_table[["healthy_label", feature, anchor]].copy()
    clean[feature] = pd.to_numeric(clean[feature], errors="coerce")
    clean[anchor] = pd.to_numeric(clean[anchor], errors="coerce")
    clean["healthy_label"] = pd.to_numeric(clean["healthy_label"], errors="coerce")
    clean = clean.dropna()
    n = int(len(clean))
    if n < 6 or clean["healthy_label"].nunique() < 2 or clean[feature].nunique() < 2:
        return {"beta": None, "p_value": None, "n": n}
    x = clean[feature].to_numpy(dtype=float)
    group = clean["healthy_label"].to_numpy(dtype=float)
    y = clean[anchor].to_numpy(dtype=float)
    design = np.column_stack([np.ones(n), x, group, x * group])
    rank = int(np.linalg.matrix_rank(design))
    if rank < design.shape[1]:
        return {"beta": None, "p_value": None, "n": n}
    beta, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ beta
    dof = n - design.shape[1]
    if dof <= 0:
        return {"beta": float(beta[3]), "p_value": None, "n": n}
    sigma2 = float(np.dot(residuals, residuals) / dof)
    covariance = sigma2 * np.linalg.inv(design.T @ design)
    se = float(math.sqrt(max(covariance[3, 3], 0.0)))
    if se <= 0 or not math.isfinite(se):
        return {"beta": float(beta[3]), "p_value": None, "n": n}
    t_value = float(beta[3] / se)
    p_value = float(2.0 * stats.t.sf(abs(t_value), dof))
    return {"beta": float(beta[3]), "p_value": p_value, "n": n}


def _benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    indexed = [(idx, float(p)) for idx, p in enumerate(p_values) if p is not None and p == p]
    q_values: list[float | None] = [None] * len(p_values)
    if not indexed:
        return q_values
    indexed.sort(key=lambda item: item[1])
    m = len(indexed)
    previous = 1.0
    for rank, (idx, p_value) in reversed(list(enumerate(indexed, start=1))):
        q_value = min(previous, p_value * m / rank)
        q_values[idx] = float(min(q_value, 1.0))
        previous = q_value
    return q_values


def _safe_filename(value: str) -> str:
    safe = []
    for char in str(value):
        safe.append(char if char.isalnum() or char in {"-", "_"} else "_")
    return "".join(safe).strip("_") or "anchor"


def _feature_networks(feature: str) -> tuple[str, str]:
    name = feature.removesuffix("_FC")
    parts = name.split("_")
    if len(parts) >= 2:
        return parts[0], "_".join(parts[1:])
    return name, name


def _plot_connection_circle(
    table: pd.DataFrame,
    *,
    value_column: str,
    title: str,
    path: Path,
    highlight_column: str | None,
    kind: str,
) -> dict[str, str]:
    rows = table.copy()
    if highlight_column and highlight_column in rows.columns:
        rows = rows[rows[highlight_column].fillna(False).astype(bool)]
    if _try_mne_connection_circle(rows, table, value_column=value_column, title=title, path=path):
        return {"kind": kind, "path": str(path), "renderer": "mne"}
    fig, ax = plt.subplots(figsize=(6.4, 6.0), constrained_layout=True)
    ax.set_aspect("equal")
    ax.axis("off")
    networks = _networks_from_rows(rows if not rows.empty else table)
    coords = _circle_coords(networks)
    for network, (x, y) in coords.items():
        ax.scatter([x], [y], s=420, color="#f8fafc", edgecolor="#334155", linewidth=1.4, zorder=3)
        ax.text(x, y, network, ha="center", va="center", fontsize=9, zorder=4)
    if rows.empty:
        ax.text(0, 0, "No FDR-significant connections", ha="center", va="center", fontsize=11, color="#64748b")
    else:
        max_abs = max(1e-9, float(pd.to_numeric(rows[value_column], errors="coerce").abs().max()))
        for _, row in rows.iterrows():
            left, right = str(row["network_a"]), str(row["network_b"])
            if left not in coords or right not in coords:
                continue
            value = float(row.get(value_column) or 0.0)
            color = "#b91c1c" if value >= 0 else "#2563eb"
            width = 0.8 + 5.0 * abs(value) / max_abs
            ax.plot([coords[left][0], coords[right][0]], [coords[left][1], coords[right][1]], color=color, linewidth=width, alpha=0.72, zorder=2)
    ax.set_title(title, pad=16)
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return {"kind": kind, "path": str(path), "renderer": "matplotlib_fallback"}


def _plot_connection_connectome(
    table: pd.DataFrame,
    *,
    value_column: str,
    title: str,
    path: Path,
    highlight_column: str | None,
    kind: str,
    node_coordinates: pd.DataFrame | None = None,
) -> dict[str, str]:
    rows = table.copy()
    if highlight_column and highlight_column in rows.columns:
        rows = rows[rows[highlight_column].fillna(False).astype(bool)]
    if _try_nilearn_connectome(rows, table, value_column=value_column, title=title, path=path, node_coordinates=node_coordinates):
        return {"kind": kind, "path": str(path), "renderer": "nilearn_connectome"}
    return {"kind": kind, "path": str(path), "renderer": "nilearn_unavailable"}


def _plot_connection_connectome_3d(
    table: pd.DataFrame,
    *,
    value_column: str,
    title: str,
    path: Path,
    highlight_column: str | None,
    kind: str,
    node_coordinates: pd.DataFrame | None = None,
) -> dict[str, str]:
    rows = table.copy()
    if highlight_column and highlight_column in rows.columns:
        rows = rows[rows[highlight_column].fillna(False).astype(bool)]
    if _try_nilearn_connectome_3d(rows, table, value_column=value_column, title=title, path=path, node_coordinates=node_coordinates):
        return {"kind": kind, "path": str(path), "renderer": "nilearn_connectome_3d"}
    if _try_plotly_connectome_3d(rows, table, value_column=value_column, title=title, path=path, node_coordinates=node_coordinates):
        return {"kind": kind, "path": str(path), "renderer": "plotly_3d_connectome"}
    return {"kind": kind, "path": str(path), "renderer": "plotly_unavailable"}


def _try_mne_connection_circle(
    rows: pd.DataFrame,
    full_table: pd.DataFrame,
    *,
    value_column: str,
    title: str,
    path: Path,
) -> bool:
    try:
        from mne.viz import circular_layout, plot_connectivity_circle
    except Exception:
        return False
    networks = _networks_from_rows(rows if not rows.empty else full_table)
    index = {network: idx for idx, network in enumerate(networks)}
    matrix = np.zeros((len(networks), len(networks)), dtype=float)
    for _, row in rows.iterrows():
        left, right = str(row["network_a"]), str(row["network_b"])
        if left not in index or right not in index:
            continue
        if left == right:
            continue
        value = float(row.get(value_column) or 0.0)
        matrix[index[left], index[right]] = value
        matrix[index[right], index[left]] = value
    try:
        node_angles = circular_layout(networks, networks, start_pos=90)
        fig, _ = plot_connectivity_circle(
            matrix,
            networks,
            node_angles=node_angles,
            title=title,
            show=False,
            colormap="coolwarm",
            facecolor="white",
            textcolor="black",
            node_edgecolor="black",
        )
        fig.savefig(path, dpi=180)
        plt.close(fig)
        return True
    except Exception:
        return False


def _try_plotly_connectome_3d(
    rows: pd.DataFrame,
    full_table: pd.DataFrame,
    *,
    value_column: str,
    title: str,
    path: Path,
    node_coordinates: pd.DataFrame | None = None,
) -> bool:
    try:
        import plotly.graph_objects as go
    except Exception:
        return False
    networks = _networks_from_rows(rows if not rows.empty else full_table)
    coords = _coords_by_network(networks, node_coordinates)
    traces: list[Any] = []
    values = pd.to_numeric(rows[value_column], errors="coerce") if value_column in rows.columns else pd.Series(dtype=float)
    max_abs = max(1e-9, float(values.abs().max())) if not values.empty and values.notna().any() else 1.0
    for _, row in rows.iterrows():
        left, right = str(row["network_a"]), str(row["network_b"])
        if left not in coords or right not in coords:
            continue
        if left == right:
            continue
        value = float(row.get(value_column) or 0.0)
        left_coord = coords[left]
        right_coord = coords[right]
        color = "#b91c1c" if value >= 0 else "#2563eb"
        width = 2.0 + 8.0 * abs(value) / max_abs
        traces.append(
            go.Scatter3d(
                x=[left_coord[0], right_coord[0]],
                y=[left_coord[1], right_coord[1]],
                z=[left_coord[2], right_coord[2]],
                mode="lines",
                line={"color": color, "width": width},
                hovertemplate=f"{left} - {right}<br>{value_column}: {value:.4g}<extra></extra>",
                showlegend=False,
            )
        )
    node_x = [coords[network][0] for network in networks]
    node_y = [coords[network][1] for network in networks]
    node_z = [coords[network][2] for network in networks]
    traces.append(
        go.Scatter3d(
            x=node_x,
            y=node_y,
            z=node_z,
            mode="markers+text",
            text=networks,
            textposition="top center",
            marker={"size": 7, "color": "#f8fafc", "line": {"color": "#111827", "width": 2}},
            hovertemplate="%{text}<br>x=%{x}, y=%{y}, z=%{z}<extra></extra>",
            showlegend=False,
        )
    )
    annotation = "No nonzero connections" if rows.empty else ""
    fig = go.Figure(data=traces)
    fig.update_layout(
        title=title if not annotation else f"{title}: {annotation}",
        scene={
            "xaxis_title": "MNI x",
            "yaxis_title": "MNI y",
            "zaxis_title": "MNI z",
            "aspectmode": "data",
        },
        margin={"l": 0, "r": 0, "b": 0, "t": 48},
        template="plotly_white",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    html_body = fig.to_html(include_plotlyjs=True, full_html=False)
    path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                f"  <title>{title}</title>",
                '  <meta charset="UTF-8" />',
                "</head>",
                "<body>",
                html_body,
                "</body>",
                "</html>",
            ]
        ),
        encoding="utf-8",
    )
    return True


def _try_nilearn_connectome_3d(
    rows: pd.DataFrame,
    full_table: pd.DataFrame,
    *,
    value_column: str,
    title: str,
    path: Path,
    node_coordinates: pd.DataFrame | None = None,
) -> bool:
    try:
        from matplotlib.colors import LinearSegmentedColormap
        from nilearn import plotting
    except Exception:
        return False
    networks = _networks_from_rows(rows if not rows.empty else full_table)
    if not networks:
        return False
    index = {network: idx for idx, network in enumerate(networks)}
    matrix = np.zeros((len(networks), len(networks)), dtype=float)
    for _, row in rows.iterrows():
        left, right = str(row["network_a"]), str(row["network_b"])
        if left not in index or right not in index:
            continue
        if left == right:
            continue
        value = float(row.get(value_column) or 0.0)
        matrix[index[left], index[right]] = value
        matrix[index[right], index[left]] = value
    coord_map = _coords_by_network(networks, node_coordinates)
    coords = np.array([coord_map.get(network, (0.0, 0.0, 0.0)) for network in networks], dtype=float)
    coord_source, coord_space = _coordinate_summary(node_coordinates)
    red_blue_cmap = LinearSegmentedColormap.from_list(
        "sleepagent_blue_slate_red_connectome",
        [(0.0, "#0057ff"), (0.5, "#64748b"), (1.0, "#ff1f1f")],
        N=256,
    )
    try:
        view = plotting.view_connectome(
            matrix,
            coords,
            edge_threshold=0.0,
            edge_cmap=red_blue_cmap,
            symmetric_cmap=True,
            linewidth=9.0,
            node_size=6.0,
            colorbar=True,
            title=title,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        view.save_as_html(str(path))
        _unwrap_nilearn_iframe_html(path)
        _inject_connectome_marker_labels(path, networks)
        _inject_connectome_explanation(path, title, rows, value_column, coord_source=coord_source, coord_space=coord_space)
        return True
    except Exception:
        return False


def _unwrap_nilearn_iframe_html(html_path: Path) -> None:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    if html.lstrip().lower().startswith("<!doctype html") or html.lstrip().lower().startswith("<html"):
        return
    start = html.find('srcdoc="')
    if start < 0:
        return
    content_start = start + len('srcdoc="')
    content_end = html.find('"', content_start)
    if content_end <= content_start:
        return
    inner = html_lib.unescape(html[content_start:content_end]).lstrip()
    if inner.startswith("<!DOCTYPE html>"):
        inner = "<!doctype html>" + inner[len("<!DOCTYPE html>") :]
    html_path.write_text(inner, encoding="utf-8")


def _inject_connectome_marker_labels(html_path: Path, labels: list[str]) -> None:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    marker_text = """text: info["marker_labels"],
            marker: {"""
    marker_text_with_style = """text: info["marker_labels"],
            textposition: info["marker_textposition"] || "top center",
            textfont: {
              size: info["marker_text_size"] || 12,
              color: info["marker_text_color"] || "#111111",
              family: "Arial, Microsoft YaHei, sans-serif",
            },
            marker: {"""
    html = html.replace(marker_text, marker_text_with_style)
    prefix = "var connectomeInfo = "
    start = html.find(prefix)
    if start >= 0:
        json_start = start + len(prefix)
        try:
            payload, payload_length = json.JSONDecoder().raw_decode(html[json_start:])
            json_end = json_start + payload_length
            connectome = payload.setdefault("connectome", {})
            connectome["marker_labels"] = labels
            connectome["marker_textposition"] = "top center"
            connectome["marker_text_size"] = 12
            connectome["marker_text_color"] = "#111111"
            html = html[:json_start] + json.dumps(payload, ensure_ascii=False) + html[json_end:]
        except Exception:
            pass
    html_path.write_text(html, encoding="utf-8")


def _inject_connectome_explanation(
    html_path: Path,
    title: str,
    rows: pd.DataFrame,
    value_column: str,
    *,
    coord_source: str,
    coord_space: str,
) -> None:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    values = pd.to_numeric(rows[value_column], errors="coerce") if value_column in rows.columns else pd.Series(dtype=float)
    positive_edges = int((values > 0).sum()) if not values.empty else 0
    negative_edges = int((values < 0).sum()) if not values.empty else 0
    mean_value = float(values.mean()) if not values.empty and values.notna().any() else 0.0
    visible_rows = rows[rows["network_a"].astype(str) != rows["network_b"].astype(str)] if {"network_a", "network_b"}.issubset(rows.columns) else rows
    visible_values = (
        pd.to_numeric(visible_rows[value_column], errors="coerce")
        if value_column in visible_rows.columns
        else pd.Series(dtype=float)
    )
    candidate_count = int(values.notna().sum()) if not values.empty else 0
    visible_count = int(visible_values.ne(0).sum()) if not visible_values.empty else 0
    self_connection_count = max(0, candidate_count - len(visible_rows))
    explanation = f"""
<section style="font-family: Arial, 'Microsoft YaHei', sans-serif; line-height: 1.6; padding: 16px 20px; border-bottom: 1px solid #ddd;">
  <h2 style="margin: 0 0 8px 0;">{title}</h2>
  <p><strong>中文说明：</strong>本图使用 Nilearn <code>plotting.view_connectome</code> 绘制 3D 脑区功能连接。节点坐标来自 atlas/ROI mask 的组级中位数 centroid，直接标注脑区/网络名称；连接线表示 grounding 锁定候选 FC 的组间差异、组内症状关系或 group × FC 交互统计量。</p>
  <p><strong>坐标来源：</strong>{coord_source}；<strong>坐标空间：</strong>{coord_space}。</p>
  <p><strong>颜色含义：</strong><span style="color:#b2182b;font-weight:700;">红色连接</span>表示 {value_column} 为正，<span style="color:#2166ac;font-weight:700;">蓝色连接</span>表示 {value_column} 为负。线条越明显，绝对值越大。</p>
  <p><strong>候选 FC 总数：</strong>{candidate_count}；<strong>图中可见跨节点连接：</strong>{visible_count}；<strong>网络内部/自连接：</strong>{self_connection_count}。</p>
  <p><strong>候选 FC 正值数：</strong>{positive_edges}；<strong>候选 FC 负值数：</strong>{negative_edges}；<strong>候选 FC 平均值：</strong>{mean_value:.4f}。</p>
</section>
"""
    body_match = html.lower().find("<body>")
    if body_match >= 0:
        insert_at = body_match + len("<body>")
        html = html[:insert_at] + explanation + html[insert_at:]
    else:
        html = explanation + html
    html_path.write_text(html, encoding="utf-8")


def _try_nilearn_connectome(
    rows: pd.DataFrame,
    full_table: pd.DataFrame,
    *,
    value_column: str,
    title: str,
    path: Path,
    node_coordinates: pd.DataFrame | None = None,
) -> bool:
    try:
        from nilearn import plotting
    except Exception:
        return False
    networks = _networks_from_rows(rows if not rows.empty else full_table)
    if not networks:
        return False
    index = {network: idx for idx, network in enumerate(networks)}
    matrix = np.zeros((len(networks), len(networks)), dtype=float)
    for _, row in rows.iterrows():
        left, right = str(row["network_a"]), str(row["network_b"])
        if left not in index or right not in index:
            continue
        if left == right:
            continue
        value = float(row.get(value_column) or 0.0)
        matrix[index[left], index[right]] = value
        matrix[index[right], index[left]] = value
    coord_map = _coords_by_network(networks, node_coordinates)
    coords = np.array([coord_map.get(network, (0.0, 0.0, 0.0)) for network in networks], dtype=float)
    try:
        if rows.empty or not np.any(matrix):
            display = plotting.plot_markers(
                np.ones(len(coords)),
                coords,
                node_size=70,
                node_cmap="Greys",
                colorbar=False,
                title=f"{title}: no nonzero connections",
                display_mode="ortho",
            )
        else:
            display = plotting.plot_connectome(
                matrix,
                coords,
                node_color="#f8fafc",
                node_size=70,
                edge_cmap="coolwarm",
                colorbar=True,
                title=title,
                display_mode="ortho",
            )
        for network, coord in zip(networks, coords, strict=False):
            display.add_markers([coord], marker_color="#f8fafc", marker_size=70)
            display.annotate(size=7)
        display.savefig(path, dpi=180)
        display.close()
        return True
    except Exception:
        return False


def _networks_from_rows(table: pd.DataFrame) -> list[str]:
    values: list[str] = []
    for column in ("network_a", "network_b"):
        if column in table.columns:
            values.extend(str(item) for item in table[column].dropna().tolist())
    ordered = [network for network in DEFAULT_NETWORK_COORDS if network in values]
    ordered.extend(network for network in sorted(set(values)) if network not in ordered)
    return ordered or list(DEFAULT_NETWORK_COORDS)


def _circle_coords(networks: list[str]) -> dict[str, tuple[float, float]]:
    coords: dict[str, tuple[float, float]] = {}
    n = max(1, len(networks))
    for idx, network in enumerate(networks):
        angle = 2 * math.pi * idx / n + math.pi / 2
        coords[network] = (math.cos(angle), math.sin(angle))
    return coords
