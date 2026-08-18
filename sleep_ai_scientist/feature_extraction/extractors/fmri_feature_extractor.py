from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sleep_ai_scientist.feature_extraction.schemas import FeatureTable

try:  # pragma: no cover - optional but available in the target neuroimaging env.
    import nibabel as nib
    from nilearn.image import index_img, resample_to_img
except Exception:  # pragma: no cover
    nib = None
    index_img = None
    resample_to_img = None


DEFAULT_NETWORK_LABELS = {
    "thalamus": [10, 49],
    "DMN": [1008, 1025, 1026, 2008, 2025, 2026],
    "salience": [1035, 2035, 1027, 2027],
    "frontoparietal": [1003, 1029, 2003, 2029],
}


class FMRIFeatureExtractor:
    """Collects fMRI features and preserves ROI/network FC columns when present."""

    DEFAULT_FEATURES = [
        "thalamus_DMN_FC",
        "thalamus_salience_FC",
        "thalamus_frontoparietal_FC",
        "DMN_FC",
        "salience_FC",
        "frontoparietal_FC",
        "DMN_salience_FC",
        "DMN_frontoparietal_FC",
        "salience_frontoparietal_FC",
        "mean_FD",
        "mean_DVARS",
        "percent_high_motion",
        "max_FD",
        "global_signal_psd_power_mean",
        "qc_signal_post_DVARS_mean",
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def run(self, *, plan_id: str, output_dir: str | Path) -> FeatureTable | None:
        output_dir = Path(output_dir)
        frame = self._extract_from_derivatives()
        source = "derivatives"
        if frame is None:
            source_path = self._find_source()
            if source_path is None:
                return None
            frame = pd.read_csv(source_path)
            source = str(source_path)
        if "subject_id" not in frame.columns:
            frame.insert(0, "subject_id", [f"row_{idx}" for idx in range(len(frame))])
        feature_columns = [
            column
            for column in frame.columns
            if column not in {"subject_id", "subject", "session", "task", "run"} and pd.api.types.is_numeric_dtype(frame[column])
        ]
        target = output_dir / "fmri_features.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(target, index=False)
        return FeatureTable(
            modality="fMRI",
            path=str(target),
            feature_columns=feature_columns,
            metadata={"source": source, "plan_id": plan_id, "roi_fc_status": "computed_when_atlas_available"},
        )

    def _find_source(self) -> Path | None:
        explicit = self.config.get("features_csv")
        if explicit and Path(explicit).exists():
            return Path(explicit)
        for key in ("output_root", "derivatives_root", "input_root"):
            root = self.config.get(key)
            if not root:
                continue
            candidates = sorted(Path(root).rglob("*fmri*features*.csv"))
            if candidates:
                return candidates[0]
        fixture = Path("data/fixtures/toy_fmri_features.csv")
        return fixture if fixture.exists() else None

    def _extract_from_derivatives(self) -> pd.DataFrame | None:
        derivatives_root = self.config.get("derivatives_root")
        if not derivatives_root:
            output_root = self.config.get("output_root")
            if output_root:
                candidate = Path(output_root) / "bids" / "derivatives" / "FMRIPREP"
                derivatives_root = str(candidate)
        if not derivatives_root:
            return None
        root = Path(derivatives_root)
        if not root.exists():
            return None
        rows: list[dict[str, Any]] = []
        subjects = {str(item) for item in self.config.get("subjects", []) if str(item)}
        subjects.update(f"sub-{item.removeprefix('sub-')}" for item in list(subjects))
        for subject_dir in sorted(path for path in root.glob("sub-*") if path.is_dir()):
            if subjects and subject_dir.name not in subjects:
                continue
            for session_dir in sorted(path for path in subject_dir.glob("ses-*") if path.is_dir()):
                for qc_csv in sorted((session_dir / "qc_statistics").glob("*desc-carpetplotSignalComparison.csv")):
                    row = self._row_from_qc(subject_dir, session_dir, qc_csv)
                    row.update(self._time_frequency_features(session_dir, qc_csv))
                    row.update(self._roi_fc_features(subject_dir, session_dir, qc_csv))
                    rows.append(row)
        if not rows:
            return None
        return pd.DataFrame(rows)

    def _row_from_qc(self, subject_dir: Path, session_dir: Path, qc_csv: Path) -> dict[str, Any]:
        subject = subject_dir.name
        session = session_dir.name
        task = _task_from_name(qc_csv.name)
        row: dict[str, Any] = {
            "subject_id": f"{subject}_{session}_{task}" if task else f"{subject}_{session}",
            "subject": subject,
            "session": session,
            "task": task,
        }
        frame = pd.read_csv(qc_csv)
        for _, item in frame.iterrows():
            signal = str(item.get("signal", "")).strip()
            if not signal:
                continue
            prefix = signal.replace(" ", "_")
            for column in ["pre_mean", "post_mean", "mean_delta", "pre_sigma", "post_sigma", "sigma_delta", "sigma_reduction_percent", "pre_max", "post_max"]:
                value = item.get(column)
                row[f"qc_signal_{prefix}_{column}"] = _as_float(value)
        row["mean_FD"] = row.get("qc_signal_FD_pre_mean")
        row["max_FD"] = row.get("qc_signal_FD_pre_max")
        row["mean_DVARS"] = row.get("qc_signal_DVARS_post_mean")
        row["qc_signal_post_DVARS_mean"] = row.get("qc_signal_DVARS_post_mean")
        row["qc_signal_post_GS_mean"] = row.get("qc_signal_GS_post_mean")

        ts_candidates = sorted((session_dir / "qc_statistics").glob(f"*{task}*desc-carpetplot_timeseries.csv")) if task else []
        if not ts_candidates:
            ts_candidates = sorted((session_dir / "qc_statistics").glob("*desc-carpetplot_timeseries.csv"))
        if ts_candidates:
            ts = pd.read_csv(ts_candidates[0])
            if "pre_FD" in ts:
                row["percent_high_motion"] = float((pd.to_numeric(ts["pre_FD"], errors="coerce") > 0.5).mean())
            if "post_DVARS" in ts:
                row["post_DVARS_std"] = float(pd.to_numeric(ts["post_DVARS"], errors="coerce").std())
        return row

    def _time_frequency_features(self, session_dir: Path, qc_csv: Path) -> dict[str, Any]:
        task = _task_from_name(qc_csv.name)
        features: dict[str, Any] = {}
        summary_candidates = sorted((session_dir / "time_frequency").glob(f"*{task}*alff_falff_summary.json")) if task else []
        if not summary_candidates:
            summary_candidates = sorted((session_dir / "time_frequency").glob("*alff_falff_summary.json"))
        if summary_candidates:
            try:
                payload = json.loads(summary_candidates[0].read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            _flatten_numeric(payload, "timefreq", features)
        psd_candidates = sorted((session_dir / "time_frequency").glob(f"*{task}*global_signal_psd.csv")) if task else []
        if not psd_candidates:
            psd_candidates = sorted((session_dir / "time_frequency").glob("*global_signal_psd.csv"))
        if psd_candidates:
            psd = pd.read_csv(psd_candidates[0])
            numeric = psd.select_dtypes(include=["number"])
            if not numeric.empty:
                value_columns = [column for column in numeric.columns if column.lower() not in {"frequency", "freq", "hz"}]
                if value_columns:
                    values = numeric[value_columns].to_numpy().ravel()
                    features["global_signal_psd_power_mean"] = float(np.nanmean(values))
                    features["global_signal_psd_power_max"] = float(np.nanmax(values))
        return features

    def _roi_fc_features(self, subject_dir: Path, session_dir: Path, qc_csv: Path) -> dict[str, Any]:
        if nib is None or resample_to_img is None or index_img is None:
            return {"roi_fc_status": "nilearn_unavailable"}
        task = _task_from_name(qc_csv.name)
        bold_candidates = sorted((session_dir / "clean_data" / "volume").glob(f"*{task}*_12rp_50pca_csf_wm.nii.gz")) if task else []
        if not bold_candidates:
            bold_candidates = sorted((session_dir / "clean_data" / "volume").glob("*_12rp_50pca_csf_wm.nii.gz"))
        atlas_candidates = _atlas_candidates(subject_dir, session_dir)
        if not bold_candidates:
            return {"roi_fc_status": "missing_bold"}
        if not atlas_candidates:
            return {"roi_fc_status": "missing_atlas"}
        try:
            bold_img = nib.load(str(bold_candidates[0]))
            atlas_img = nib.load(str(atlas_candidates[0]))
            atlas_resampled = resample_to_img(atlas_img, index_img(bold_img, 0), interpolation="nearest", force_resample=True, copy_header=True)
            atlas = np.asarray(atlas_resampled.get_fdata(), dtype=np.int32)
            bold = np.asarray(bold_img.get_fdata(), dtype=np.float32)
            networks = DEFAULT_NETWORK_LABELS
            timeseries = {name: _network_timeseries(bold, atlas, labels) for name, labels in networks.items()}
            centroids = _network_centroids(atlas, atlas_resampled.affine, networks)
            features: dict[str, Any] = {
                "roi_fc_status": "computed",
                "roi_coord_source": str(atlas_candidates[0]),
                "roi_coord_space": _coordinate_space_from_path(atlas_candidates[0]),
            }
            for name, series in timeseries.items():
                features[f"{name}_roi_voxels"] = int(np.isfinite(series).sum()) if series.size else 0
            for name, coord in centroids.items():
                features[f"{name}_coord_x"] = coord[0]
                features[f"{name}_coord_y"] = coord[1]
                features[f"{name}_coord_z"] = coord[2]
            pairs = [
                ("thalamus", "DMN", "thalamus_DMN_FC"),
                ("thalamus", "salience", "thalamus_salience_FC"),
                ("thalamus", "frontoparietal", "thalamus_frontoparietal_FC"),
                ("DMN", "salience", "DMN_salience_FC"),
                ("DMN", "frontoparietal", "DMN_frontoparietal_FC"),
                ("salience", "frontoparietal", "salience_frontoparietal_FC"),
            ]
            for left, right, column in pairs:
                features[column] = _fisher_corr(timeseries.get(left), timeseries.get(right))
            features["DMN_FC"] = _within_network_proxy(timeseries.get("DMN"))
            features["salience_FC"] = _within_network_proxy(timeseries.get("salience"))
            features["frontoparietal_FC"] = _within_network_proxy(timeseries.get("frontoparietal"))
            return features
        except Exception as exc:  # pragma: no cover - depends on real neuroimaging files.
            return {"roi_fc_status": f"failed:{type(exc).__name__}"}


def _task_from_name(name: str) -> str:
    for part in name.split("_"):
        if part.startswith("task-"):
            return part
    return ""


def _atlas_candidates(subject_dir: Path, session_dir: Path) -> list[Path]:
    """Find fMRIPrep aparcaseg outputs across subject- and session-level layouts."""
    base = subject_dir / "fmriprep" / "output" / subject_dir.name
    patterns = [
        base / session_dir.name / "anat",
        base / "anat",
    ]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for directory in patterns:
        for path in sorted(directory.glob("*desc-aparcaseg_dseg.nii.gz")):
            if path not in seen:
                seen.add(path)
                candidates.append(path)
    if candidates:
        return candidates
    for path in sorted(base.rglob("*desc-aparcaseg_dseg.nii.gz")) if base.exists() else []:
        if path not in seen:
            seen.add(path)
            candidates.append(path)
    return candidates


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def _flatten_numeric(payload: dict[str, Any], prefix: str, output: dict[str, Any]) -> None:
    for key, value in payload.items():
        name = f"{prefix}_{key}".replace(" ", "_")
        if isinstance(value, dict):
            _flatten_numeric(value, name, output)
        else:
            numeric = _as_float(value)
            if numeric is not None:
                output[name] = numeric


def _network_timeseries(bold: np.ndarray, atlas: np.ndarray, labels: list[int]) -> np.ndarray:
    mask = np.isin(atlas, labels)
    if not mask.any() or bold.ndim != 4:
        return np.array([])
    data = bold[mask, :]
    return np.nanmean(data, axis=0)


def _network_centroids(
    atlas: np.ndarray,
    affine: np.ndarray,
    networks: dict[str, list[int]],
) -> dict[str, tuple[float, float, float]]:
    centroids: dict[str, tuple[float, float, float]] = {}
    for name, labels in networks.items():
        voxel_indices = np.argwhere(np.isin(atlas, labels))
        if voxel_indices.size == 0:
            continue
        homogeneous = np.c_[voxel_indices, np.ones(len(voxel_indices))]
        world = homogeneous @ np.asarray(affine, dtype=float).T
        centroid = np.nanmean(world[:, :3], axis=0)
        if np.all(np.isfinite(centroid)):
            centroids[name] = (float(centroid[0]), float(centroid[1]), float(centroid[2]))
    return centroids


def _coordinate_space_from_path(path: Path) -> str:
    name = path.name
    for part in name.split("_"):
        if part.startswith("space-"):
            return part.removeprefix("space-")
    return "atlas_image_world"


def _fisher_corr(left: np.ndarray | None, right: np.ndarray | None) -> float | None:
    if left is None or right is None or len(left) < 4 or len(right) < 4:
        return None
    corr = np.corrcoef(left, right)[0, 1]
    if not np.isfinite(corr):
        return None
    corr = float(np.clip(corr, -0.999999, 0.999999))
    return float(np.arctanh(corr))


def _within_network_proxy(series: np.ndarray | None) -> float | None:
    if series is None or len(series) < 4:
        return None
    return float(np.nanstd(series))
