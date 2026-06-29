from __future__ import annotations

import csv
import html
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


PARADIGM = {'id': 'behavioral_computational_modeling',
 'name': 'Behavioral computational modeling',
 'keywords': ['behavior',
              'reaction time',
              'accuracy',
              'reinforcement learning',
              'drift diffusion',
              '行为',
              '反应时',
              '正确率',
              '计算模型'],
 'required_data': ['behavior'],
 'outputs': ['behavior_summary', 'model_fit_table', 'candidate_predictors'],
 'template': 'behavioral_computational_modeling.py',
 'prompt_match_score': 0,
 'data_compatibility_score': 20,
 'missing_data': [],
 'executable': True,
 'selection_score': 20}
EXPERIMENT_PLAN = {'说明': '实验代码生成计划：从创新点和假设出发，明确可测量输出、分析步骤、风险控制，并在执行后用于反向更新创新点。',
 'paradigm_id': 'behavioral_computational_modeling',
 'paradigm_name': 'Behavioral computational modeling',
 'linked_innovations': [{'id': 'innovation_07',
                         'paradigm_id': 'dynamic_functional_connectivity+graph_theory_connectomics+behavioral_computational_modeling',
                         'hypothesis': '当认知负荷（Cognitive Load, '
                                       'CL）从低到高增加时，大脑网络会经历一个从低整合、高模块化的初始状态（S1）向高整合、低模块化、且默认模式网络（DMN）与任务相关网络（TPN）连接增强的全局整合状态（S2）的显著状态转移。这种状态转移的速率（$\t'
                                       'ext{Rate}(S1 \to '
                                       'S2)$）与任务难度增加带来的认知负荷增加呈正相关，且该转移速率的瓶颈区域是DMN与TPN连接的增强。',
                         'innovation_point': '构建一个基于隐马尔可夫模型（HMM）的动态网络拓扑重组分析框架，将实时行为指标（如N-back任务的准确率或反应时）作为外部时变协变量，量化网络从不同拓扑状态（如模块化系数$Q$和全局效率$E$）向高整合状态转移的**状态转移概率**和**临界重组速率**。创新点在于用行为指标驱动网络状态转换的动力学模型，而非仅报告静态状态。',
                         'experimental_plan': [],
                         'testable_outputs': ['behavior_summary',
                                              'candidate_predictors',
                                              'connectome_summary',
                                              'graph_metrics',
                                              'model_fit_table',
                                              'state_features',
                                              'windowed_fc'],
                         'risk_factors': []}],
 'analysis_goal_zh': '用 Behavioral computational modeling 的可执行输出检验关联创新点中的神经科学假设。',
 'measurable_outputs': ['behavior_summary', 'model_fit_table', 'candidate_predictors'],
 'required_data': ['behavior'],
 'missing_data': [],
 'analysis_steps_zh': ['检查输入目录中的被试、session 和可用数据类型。',
                       '运行该 paradigm 对应的分析函数，生成结构化 result.json。',
                       '提取关键指标、输出图表或中间表格。',
                       '记录失败原因、缺失数据和解释边界，供创新点反向更新使用。'],
 'risk_controls_zh': ['如果缺失必要数据，则将结果标记为 not_executable，而不是强行得出结论。',
                      '如果分析脚本失败或超时，后续创新点更新只解释可执行性风险，不把失败当作科学反证。',
                      '所有 result.json 中的指标都作为后续 LLM 反向更新的证据来源。']}

LAST_REGION_LABELS: list[str] = []
LAST_COORDINATE_QC: dict[str, Any] = {}


def configure_runtime_cache() -> None:
    cache_root = Path(os.environ.get("NEURO_RESEARCH_AGENT_CACHE", "/tmp/neuro_research_agent_cache"))
    matplotlib_cache = cache_root / "matplotlib"
    xdg_cache = cache_root / "xdg"
    fontconfig_cache = xdg_cache / "fontconfig"
    for path in (matplotlib_cache, xdg_cache, fontconfig_cache):
        path.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(xdg_cache))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def subject_alias(subject: str | None) -> str | None:
    if not subject:
        return None
    return subject if subject.startswith("sub-") else f"sub-{subject}"


def iter_sessions(input_root: Path, subject: str | None, session: str | None) -> list[Path]:
    sub = subject_alias(subject)
    search_roots = [input_root]
    if (input_root / "derivatives").exists():
        search_roots.append(input_root / "derivatives")
    if input_root.name != "derivatives" and input_root.parent.name == "derivatives":
        search_roots.append(input_root.parent)
    subject_dirs = []
    if sub:
        for root in search_roots:
            subject_dirs.append(root / sub)
    else:
        for root in search_roots:
            subject_dirs.extend(sorted(root.glob("sub-*")))
    sessions: list[Path] = []
    for subject_dir in subject_dirs:
        if not subject_dir.exists():
            continue
        for ses_dir in sorted(subject_dir.glob("ses-*")):
            if session and ses_dir.name != session:
                continue
            sessions.append(ses_dir)
    return sessions


def find_clean_bold(input_root: Path, subject: str | None, session: str | None) -> list[Path]:
    files: list[Path] = []
    for ses_dir in iter_sessions(input_root, subject, session):
        files.extend(sorted((ses_dir / "clean_data" / "volume").glob("*.nii.gz")))
    return files


def find_surface_bold(input_root: Path, subject: str | None, session: str | None) -> list[Path]:
    files: list[Path] = []
    for ses_dir in iter_sessions(input_root, subject, session):
        files.extend(sorted((ses_dir / "clean_data" / "surface").glob("*.func.gii")))
    return files


def find_events(input_root: Path, subject: str | None, session: str | None) -> list[Path]:
    files: list[Path] = []
    for ses_dir in iter_sessions(input_root, subject, session):
        files.extend(sorted(ses_dir.rglob("*events.tsv")))
    return files


def find_segments(input_root: Path, subject: str | None, session: str | None) -> list[Path]:
    files: list[Path] = []
    for ses_dir in iter_sessions(input_root, subject, session):
        path = ses_dir / "segment" / "segment_summary.json"
        if path.exists():
            files.append(path)
    return files


def find_segment_bold(input_root: Path, subject: str | None, session: str | None) -> list[Path]:
    files: list[Path] = []
    for ses_dir in iter_sessions(input_root, subject, session):
        files.extend(sorted((ses_dir / "segment" / "clean_data" / "volume").glob("S_*.nii.gz")))
        files.extend(sorted((ses_dir / "segment" / "clean_data" / "volume").glob("W_*.nii.gz")))
    return sorted(files)


def load_bold(path: Path) -> tuple[np.ndarray, dict[str, Any], np.ndarray]:
    try:
        import nibabel as nib
    except Exception as exc:
        raise RuntimeError(f"nibabel is required to load NIfTI files: {exc}") from exc
    img = nib.load(str(path))
    data = np.asarray(img.get_fdata(dtype=np.float32))
    if data.ndim != 4:
        raise RuntimeError(f"Expected 4D BOLD image, got shape {data.shape}")
    zooms = img.header.get_zooms()
    tr = float(zooms[3]) if len(zooms) > 3 and zooms[3] else 2.0
    return data, {"shape": list(data.shape), "tr": tr}, np.asarray(img.affine, dtype=float)


def subject_session_from_path(path: Path) -> tuple[str | None, str | None]:
    subject = next((parent.name for parent in path.parents if parent.name.startswith("sub-")), None)
    session = next((parent.name for parent in path.parents if parent.name.startswith("ses-")), None)
    return subject, session


def fmriprep_subject_dir(path: Path) -> Path | None:
    subject, _session = subject_session_from_path(path)
    subject_root = next((parent for parent in path.parents if parent.name == subject), None) if subject else None
    if subject_root is None:
        return None
    candidate = subject_root / "fmriprep" / "output" / subject
    return candidate if candidate.exists() else None


def find_func_brain_mask(path: Path) -> Path | None:
    subject, session = subject_session_from_path(path)
    subject_dir = fmriprep_subject_dir(path)
    if subject_dir is None or session is None:
        return None
    func_dir = subject_dir / session / "func"
    patterns = [
        f"{subject}_{session}_*_space-T1w_desc-brain_mask.nii.gz",
        f"{subject}_{session}_*_desc-brain_mask.nii.gz",
    ]
    for pattern in patterns:
        matches = sorted(func_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def find_gm_probseg(path: Path) -> Path | None:
    subject, _session = subject_session_from_path(path)
    subject_dir = fmriprep_subject_dir(path)
    if subject_dir is None or subject is None:
        return None
    candidates = [
        subject_dir / "anat" / f"{subject}_label-GM_probseg.nii.gz",
        subject_dir / "anat" / f"{subject}_space-MNI152NLin2009cAsym_res-2_label-GM_probseg.nii.gz",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = sorted((subject_dir / "anat").glob(f"{subject}*label-GM_probseg.nii.gz"))
    return matches[0] if matches else None


def fmriprep_output_dir(path: Path) -> Path | None:
    subject, _session = subject_session_from_path(path)
    subject_dir = fmriprep_subject_dir(path)
    if subject is None or subject_dir is None:
        return None
    return subject_dir.parent


def find_aparcaseg(path: Path) -> Path | None:
    subject, _session = subject_session_from_path(path)
    subject_dir = fmriprep_subject_dir(path)
    if subject_dir is None or subject is None:
        return None
    candidates = [
        subject_dir / "anat" / f"{subject}_desc-aparcaseg_dseg.nii.gz",
        subject_dir / "anat" / f"{subject}_space-MNI152NLin2009cAsym_res-2_desc-aparcaseg_dseg.nii.gz",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = sorted((subject_dir / "anat").glob(f"{subject}*aparcaseg*dseg.nii.gz"))
    return matches[0] if matches else None


def find_aparcaseg_table(path: Path) -> Path | None:
    output_dir = fmriprep_output_dir(path)
    if output_dir is None:
        return None
    candidate = output_dir / "desc-aparcaseg_dseg.tsv"
    if candidate.exists():
        return candidate
    matches = sorted(output_dir.glob("*aparcaseg*dseg.tsv"))
    return matches[0] if matches else None


def load_label_table(path: Path | None) -> dict[int, str]:
    if path is None or not path.exists():
        return {}
    labels: dict[int, str] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                labels[int(row["index"])] = row.get("name", "").strip().strip('"')
            except Exception:
                continue
    return labels


def is_anatomical_roi(label_index: int, label_name: str) -> bool:
    name = label_name.lower()
    if label_index in {1000, 2000}:
        return False
    if 1000 < label_index < 1040 or 2000 < label_index < 2040:
        return True
    subcortical = {
        "left-thalamus", "right-thalamus", "left-caudate", "right-caudate",
        "left-putamen", "right-putamen", "left-pallidum", "right-pallidum",
        "left-hippocampus", "right-hippocampus", "left-amygdala", "right-amygdala",
        "left-accumbens", "right-accumbens",
    }
    return any(name.startswith(prefix) for prefix in subcortical)


def atlas_parcel_timeseries(path: Path, parcel_count: int = 12) -> tuple[np.ndarray, np.ndarray, dict[str, Any]] | None:
    try:
        import nibabel as nib
        from nibabel.processing import resample_from_to
    except Exception:
        return None
    atlas_path = find_aparcaseg(path)
    label_table = load_label_table(find_aparcaseg_table(path))
    if atlas_path is None or not label_table:
        return None
    data, meta, affine = load_bold(path)
    atlas_img = resample_from_to(nib.load(str(atlas_path)), (data.shape[:3], affine), order=0)
    atlas = np.asarray(atlas_img.get_fdata(), dtype=np.int32)
    flat = data.reshape((-1, data.shape[-1]))
    finite = np.isfinite(flat).all(axis=1)
    variable = np.nanstd(flat, axis=1) > 1e-6
    atlas_flat = atlas.reshape(-1)
    ijk_all = np.column_stack(np.unravel_index(np.arange(atlas_flat.size), data.shape[:3]))
    xyz_all = (np.c_[ijk_all, np.ones(ijk_all.shape[0])] @ affine.T)[:, :3]
    candidates: list[tuple[int, str, np.ndarray]] = []
    for label_index, label_name in label_table.items():
        if not is_anatomical_roi(label_index, label_name):
            continue
        voxels = np.where((atlas_flat == label_index) & finite & variable)[0]
        if voxels.size >= 8:
            candidates.append((label_index, label_name, voxels))
    if len(candidates) < 4:
        return None
    candidates.sort(key=lambda item: item[2].size, reverse=True)
    selected_rois = candidates[:parcel_count]
    selected_rois.sort(key=lambda item: (float(np.mean(xyz_all[item[2], 0])), float(np.mean(xyz_all[item[2], 1]))))
    signals = []
    coords = []
    labels = []
    for label_index, label_name, voxels in selected_rois:
        signals.append(np.nanmean(flat[voxels].astype(np.float64), axis=0))
        center = np.nanmean(xyz_all[voxels], axis=0)
        representative = voxels[int(np.nanargmin(np.sum((xyz_all[voxels] - center) ** 2, axis=1)))]
        coords.append(xyz_all[representative])
        labels.append(label_name.replace("ctx-lh-", "L-").replace("ctx-rh-", "R-"))
    ts = np.vstack(signals)
    node_coords = np.vstack(coords)
    ts = ts - ts.mean(axis=1, keepdims=True)
    std = ts.std(axis=1, keepdims=True)
    ts = np.divide(ts, std, out=np.zeros_like(ts), where=std > 0)
    global LAST_REGION_LABELS
    LAST_REGION_LABELS = labels
    meta.update({
        "voxel_count": int(sum(item[2].size for item in selected_rois)),
        "parcel_count": int(ts.shape[0]),
        "frame_count": int(ts.shape[1]),
        "bold_file": str(path),
        "roi_source": "fmriprep_aparcaseg",
        "atlas_file": str(atlas_path),
        "region_labels": labels,
    })
    return ts, node_coords, meta


def resampled_mask(mask_path: Path, target_shape: tuple[int, int, int], target_affine: np.ndarray, threshold: float, continuous: bool) -> np.ndarray | None:
    try:
        import nibabel as nib
        from nilearn import image
        from scipy import ndimage
    except Exception:
        return None
    target = nib.Nifti1Image(np.zeros(target_shape, dtype=np.float32), target_affine)
    source = nib.load(str(mask_path))
    interpolation = "continuous" if continuous else "nearest"
    try:
        aligned = image.resample_to_img(source, target, interpolation=interpolation, force_resample=True, copy_header=True)
    except TypeError:
        aligned = image.resample_to_img(source, target, interpolation=interpolation)
    data = np.asarray(aligned.get_fdata(), dtype=float)
    mask = data > threshold
    if not continuous and mask.any() and mask.sum() > 100:
        eroded = ndimage.binary_erosion(mask, iterations=1)
        if eroded.sum() > 100:
            mask = eroded
    return mask


def analysis_voxel_mask(path: Path, target_shape: tuple[int, int, int], target_affine: np.ndarray) -> tuple[np.ndarray | None, dict[str, Any]]:
    brain_path = find_func_brain_mask(path)
    gm_path = find_gm_probseg(path)
    masks: list[np.ndarray] = []
    sources: list[str] = []
    if brain_path is not None:
        brain = resampled_mask(brain_path, target_shape, target_affine, threshold=0.5, continuous=False)
        if brain is not None and brain.any():
            masks.append(brain)
            sources.append(str(brain_path))
    if gm_path is not None:
        gm = resampled_mask(gm_path, target_shape, target_affine, threshold=0.35, continuous=True)
        if gm is not None and gm.any():
            masks.append(gm)
            sources.append(str(gm_path))
    if not masks:
        return None, {"mask_sources": []}
    combined = masks[0].copy()
    for mask in masks[1:]:
        candidate = combined & mask
        if candidate.sum() > 100:
            combined = candidate
    return combined, {"mask_sources": sources, "mask_voxel_count": int(combined.sum())}


def spatial_parcel_groups(coords: np.ndarray, parcel_count: int) -> list[np.ndarray]:
    n_clusters = min(parcel_count, max(2, coords.shape[0] // 10))
    scale = np.nanstd(coords, axis=0)
    scaled = (coords - np.nanmean(coords, axis=0)) / np.where(scale > 0, scale, 1.0)
    centers = [int(np.argmin(scaled[:, 0] + 0.2 * scaled[:, 1]))]
    for _ in range(1, n_clusters):
        dist = np.min(np.sum((scaled[:, None, :] - scaled[centers][None, :, :]) ** 2, axis=2), axis=1)
        centers.append(int(np.argmax(dist)))
    labels = np.zeros(scaled.shape[0], dtype=int)
    center_values = scaled[centers].copy()
    for _ in range(20):
        labels = np.argmin(np.sum((scaled[:, None, :] - center_values[None, :, :]) ** 2, axis=2), axis=1)
        new_centers = center_values.copy()
        for idx in range(n_clusters):
            members = scaled[labels == idx]
            if members.size:
                new_centers[idx] = np.mean(members, axis=0)
        if np.allclose(new_centers, center_values):
            break
        center_values = new_centers
    order = sorted(range(n_clusters), key=lambda idx: (float(center_values[idx, 0]), float(center_values[idx, 1]), float(center_values[idx, 2])))
    return [np.where(labels == idx)[0] for idx in order if np.any(labels == idx)]


def parcel_timeseries(path: Path, parcel_count: int = 12, max_voxels: int = 12000) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    atlas_result = atlas_parcel_timeseries(path, parcel_count)
    if atlas_result is not None:
        return atlas_result
    data, meta, affine = load_bold(path)
    flat = data.reshape((-1, data.shape[-1]))
    finite = np.isfinite(flat).all(axis=1)
    variable = np.nanstd(flat, axis=1) > 1e-6
    mask, mask_meta = analysis_voxel_mask(path, data.shape[:3], affine)
    mask_flat = mask.reshape(-1) if mask is not None else np.ones(flat.shape[0], dtype=bool)
    valid = np.where(finite & variable & mask_flat)[0]
    if valid.size < 4 and mask is not None:
        valid = np.where(finite & variable)[0]
        mask_meta["mask_fallback"] = "not_enough_masked_voxels"
    if valid.size < 4:
        raise RuntimeError("Not enough finite variable voxels for parcel summary.")
    if valid.size > max_voxels:
        stride = int(math.ceil(valid.size / max_voxels))
        valid = valid[::stride][:max_voxels]
    selected = flat[valid].astype(np.float64)
    ijk = np.column_stack(np.unravel_index(valid, data.shape[:3]))
    xyz = np.c_[ijk, np.ones(ijk.shape[0])] @ affine.T
    xyz = xyz[:, :3]
    groups = spatial_parcel_groups(xyz, parcel_count)
    signals = []
    coords = []
    for group in groups:
        if group.size:
            signals.append(np.nanmean(selected[group], axis=0))
            center = np.nanmean(xyz[group], axis=0)
            representative = group[int(np.nanargmin(np.sum((xyz[group] - center) ** 2, axis=1)))]
            coords.append(xyz[representative])
    ts = np.vstack(signals)
    node_coords = np.vstack(coords)
    ts = ts - ts.mean(axis=1, keepdims=True)
    std = ts.std(axis=1, keepdims=True)
    ts = np.divide(ts, std, out=np.zeros_like(ts), where=std > 0)
    global LAST_REGION_LABELS
    LAST_REGION_LABELS = region_labels(node_coords)
    meta.update(mask_meta)
    meta.update({"voxel_count": int(valid.size), "parcel_count": int(ts.shape[0]), "frame_count": int(ts.shape[1]), "bold_file": str(path), "roi_source": "automatic_spatial_parcels", "region_labels": LAST_REGION_LABELS})
    return ts, node_coords, meta


def corr_matrix(ts: np.ndarray) -> np.ndarray:
    matrix = np.corrcoef(ts)
    return np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)


def save_matrix(path: Path, matrix: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(path, matrix, delimiter=",", fmt="%.8f")


def region_labels(coords: np.ndarray) -> list[str]:
    if LAST_REGION_LABELS and len(LAST_REGION_LABELS) == len(coords):
        return LAST_REGION_LABELS
    if coords.size == 0:
        return []
    y_low, y_high = np.nanquantile(coords[:, 1], [0.33, 0.67])
    z_mid = float(np.nanmedian(coords[:, 2]))
    labels: list[str] = []
    counts: dict[str, int] = {}
    for coord in coords:
        lr = "L" if coord[0] < 0 else "R"
        if coord[1] <= y_low:
            ap = "Post"
        elif coord[1] >= y_high:
            ap = "Ant"
        else:
            ap = "Mid"
        si = "Sup" if coord[2] >= z_mid else "Inf"
        base = f"{lr}-{ap}-{si}"
        counts[base] = counts.get(base, 0) + 1
        labels.append(base if counts[base] == 1 else f"{base}-{counts[base]}")
    return labels


def save_roi_coords(path: Path, coords: np.ndarray, plot_coords: np.ndarray | None = None, coordinate_space: str = "source", labels: list[str] | None = None) -> None:
    labels = labels or region_labels(coords)
    display_coords = plot_coords if plot_coords is not None else coords
    rows = [
        {
            "roi": f"parcel_{idx:02d}",
            "region_name": labels[idx],
            "x": float(display_coords[idx][0]),
            "y": float(display_coords[idx][1]),
            "z": float(display_coords[idx][2]),
            "coordinate_space": coordinate_space,
            "native_x": float(coord[0]),
            "native_y": float(coord[1]),
            "native_z": float(coord[2]),
        }
        for idx, coord in enumerate(coords)
    ]
    write_csv(path, rows)


def source_space(path: Path) -> str:
    name = path.name
    match = re.search(r"_space-([^_]+)", name)
    return match.group(1) if match else "T1w"


def find_t1w_to_mni_transform(source_file: str) -> Path | None:
    path = Path(source_file)
    subject_dir = next((parent for parent in path.parents if parent.name.startswith("sub-")), None)
    if subject_dir is None:
        return None
    subject = subject_dir.name
    candidates = [
        subject_dir / "fmriprep" / "output" / subject / "anat" / f"{subject}_from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5",
        subject_dir / "fmriprep" / "output" / subject / "anat" / f"{subject}_from-T1w_to-MNI152NLin6Asym_mode-image_xfm.h5",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = sorted(subject_dir.glob(f"fmriprep/output/{subject}/anat/{subject}_from-T1w_to-MNI*_mode-image_xfm.h5"))
    return matches[0] if matches else None


def ants_transform_points(coords: np.ndarray, transform: Path) -> np.ndarray | None:
    ants_bin = shutil.which("antsApplyTransformsToPoints")
    if not ants_bin:
        return None
    with tempfile.TemporaryDirectory(prefix="neuro_coords_") as tmp:
        input_csv = Path(tmp) / "points.csv"
        output_csv = Path(tmp) / "points_mni.csv"
        ants_coords = np.asarray(coords, dtype=float).copy()
        # Nibabel/Nilearn use RAS+ world coordinates, while ANTs point transforms use LPS+.
        # Convert before and after antsApplyTransformsToPoints so the plotted MNI points
        # remain in the convention expected by Nilearn view_connectome.
        ants_coords[:, 0] *= -1
        ants_coords[:, 1] *= -1
        rows = [{"x": float(coord[0]), "y": float(coord[1]), "z": float(coord[2]), "t": 0} for coord in ants_coords]
        write_csv(input_csv, rows)
        completed = subprocess.run(
            [ants_bin, "-d", "3", "-i", str(input_csv), "-o", str(output_csv), "-t", str(transform)],
            text=True,
            capture_output=True,
            timeout=60,
        )
        if completed.returncode != 0 or not output_csv.exists():
            return None
        transformed: list[list[float]] = []
        with output_csv.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                transformed.append([float(row["x"]), float(row["y"]), float(row["z"])])
        if len(transformed) != coords.shape[0]:
            return None
        transformed_ras = np.asarray(transformed, dtype=float)
        transformed_ras[:, 0] *= -1
        transformed_ras[:, 1] *= -1
        return transformed_ras


def snap_coords_to_mni_template(coords: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    qc: dict[str, Any] = {
        "snap_applied": False,
        "snapped_node_count": 0,
        "max_snap_distance_mm": 0.0,
        "reason": "",
    }
    if coords.size == 0:
        return coords, qc
    try:
        import nibabel as nib
        from nilearn import datasets
        from scipy.spatial import cKDTree

        try:
            template = datasets.load_mni152_gm_mask(resolution=2, threshold=0.2, n_iter=2)
            data = np.asarray(template.get_fdata(), dtype=float)
            mask = np.isfinite(data) & (data > 0)
            mask_source = "MNI152 grey-matter mask"
        except Exception:
            template = datasets.load_mni152_brain_mask(resolution=2, threshold=0.2)
            data = np.asarray(template.get_fdata(), dtype=float)
            mask = np.isfinite(data) & (data > 0)
            mask_source = "MNI152 brain mask"
        if not np.any(mask):
            template = datasets.load_mni152_template(resolution=2)
            data = np.asarray(template.get_fdata(), dtype=float)
            valid = np.isfinite(data)
            positive = data[valid & (data > 0)]
            if positive.size == 0:
                qc["reason"] = "MNI template contains no positive voxels."
                return coords, qc
            threshold = float(np.nanpercentile(positive, 25))
            mask = valid & (data > threshold)
            mask_source = "MNI152 template intensity mask"
        voxels = np.argwhere(mask)
        if voxels.size == 0:
            qc["reason"] = "MNI template mask is empty after thresholding."
            return coords, qc
        world = nib.affines.apply_affine(template.affine, voxels)
        tree = cKDTree(world)
        distances, nearest = tree.query(coords)
        snap_mask = distances > 2.5
        snapped = np.array(coords, dtype=float, copy=True)
        if np.any(snap_mask):
            snapped[snap_mask] = world[nearest[snap_mask]]
        qc.update(
            {
                "snap_applied": bool(np.any(snap_mask)),
                "snapped_node_count": int(np.sum(snap_mask)),
                "max_snap_distance_mm": float(np.max(distances)) if distances.size else 0.0,
                "mean_snap_distance_mm": float(np.mean(distances)) if distances.size else 0.0,
                "snap_threshold_mm": 2.5,
                "snap_mask_source": mask_source,
                "reason": f"Coordinates farther than threshold from {mask_source} were moved to nearest in-mask voxel.",
            }
        )
        return snapped, qc
    except Exception as exc:
        qc["reason"] = f"MNI coordinate snapping unavailable: {type(exc).__name__}: {exc}"
        return coords, qc


def record_coordinate_qc(coordinate_space: str, transform_file: str | None, native_coords: np.ndarray, plot_coords: np.ndarray, snap_qc: dict[str, Any]) -> None:
    global LAST_COORDINATE_QC
    LAST_COORDINATE_QC = {
        "coordinate_space": coordinate_space,
        "transform_file": transform_file,
        "native_min": [float(value) for value in np.nanmin(native_coords, axis=0)] if native_coords.size else [],
        "native_max": [float(value) for value in np.nanmax(native_coords, axis=0)] if native_coords.size else [],
        "plot_min": [float(value) for value in np.nanmin(plot_coords, axis=0)] if plot_coords.size else [],
        "plot_max": [float(value) for value in np.nanmax(plot_coords, axis=0)] if plot_coords.size else [],
        "coordinate_convention": "Nilearn/nibabel RAS+; ANTs transforms are applied after RAS-to-LPS conversion and converted back to RAS+.",
        **snap_qc,
    }


def connectome_plot_coords(coords: np.ndarray, source_file: str) -> tuple[np.ndarray, str, str | None]:
    path = Path(source_file)
    if "space-MNI" in path.name:
        snapped, qc = snap_coords_to_mni_template(coords)
        record_coordinate_qc(source_space(path), None, coords, snapped, qc)
        return snapped, source_space(path), None
    transform = find_t1w_to_mni_transform(source_file)
    if transform is None:
        record_coordinate_qc(source_space(path), None, coords, coords, {"snap_applied": False, "snapped_node_count": 0, "reason": "No T1w-to-MNI transform found; coordinates remain in source space."})
        return coords, source_space(path), None
    transformed = ants_transform_points(coords, transform)
    if transformed is None:
        record_coordinate_qc(source_space(path), str(transform), coords, coords, {"snap_applied": False, "snapped_node_count": 0, "reason": "T1w-to-MNI transform failed; coordinates remain in source space."})
        return coords, source_space(path), str(transform)
    snapped, qc = snap_coords_to_mni_template(transformed)
    record_coordinate_qc("MNI152NLin2009cAsym", str(transform), coords, snapped, qc)
    return snapped, "MNI152NLin2009cAsym", str(transform)


def latest_coordinate_qc() -> dict[str, Any]:
    return dict(LAST_COORDINATE_QC)



def edge_summary(matrix: np.ndarray) -> dict[str, Any]:
    upper = matrix[np.triu_indices_from(matrix, k=1)]
    return {
        "positive_edge_count": int(np.sum(upper > 0)),
        "negative_edge_count": int(np.sum(upper < 0)),
        "zero_edge_count": int(np.sum(upper == 0)),
        "mean_r": float(np.mean(upper)) if upper.size else 0.0,
        "mean_positive_r": float(np.mean(upper[upper > 0])) if np.any(upper > 0) else 0.0,
        "mean_negative_r": float(np.mean(upper[upper < 0])) if np.any(upper < 0) else 0.0,
        "max_positive_r": float(np.max(upper)) if upper.size else 0.0,
        "min_negative_r": float(np.min(upper)) if upper.size else 0.0,
    }


def inject_chinese_explanation(html_path: Path, title: str, summary: dict[str, Any], source_file: str, stage_label: str, coordinate_space: str, transform_file: str | None) -> None:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    transform_note = f"；坐标变换：<code>{transform_file}</code>" if transform_file else ""
    coordinate_qc = latest_coordinate_qc()
    snap_note = ""
    if coordinate_qc.get("snap_applied"):
        snap_note = f"；为避免节点漂出模板，{coordinate_qc.get('snapped_node_count', 0)} 个节点已吸附到 MNI 模板 brain mask 内最近点，最大校正距离 {coordinate_qc.get('max_snap_distance_mm', 0.0):.2f} mm"
    explanation = f"""
<section style="font-family: Arial, 'Microsoft YaHei', sans-serif; line-height: 1.6; padding: 16px 20px; border-bottom: 1px solid #ddd;">
  <h2 style="margin: 0 0 8px 0;">{title}</h2>
  <p><strong>中文说明：</strong>本图使用 Nilearn <code>plotting.view_connectome</code> 绘制 3D 脑区功能连接。Nilearn 3D 头模使用 MNI/模板空间，因此节点绘图坐标使用 <strong>{coordinate_space}</strong> 空间{transform_note}{snap_note}；HTML 交互图中直接标注脑区名称，连接线表示 ROI 时间序列之间的 Pearson 相关系数。</p>
  <p><strong>颜色含义：</strong><span style="color:#b2182b;font-weight:700;">红色连接线表示正相关</span>，即两个脑区 BOLD 信号变化趋于同步；<span style="color:#2166ac;font-weight:700;">蓝色连接线表示负相关</span>，即两个脑区 BOLD 信号变化方向相反。颜色越深、线条越明显，表示相关强度越高。</p>
  <p><strong>阶段：</strong>{stage_label}；<strong>正相关边数：</strong>{summary.get('positive_edge_count', 0)}；<strong>负相关边数：</strong>{summary.get('negative_edge_count', 0)}；<strong>平均 r：</strong>{summary.get('mean_r', 0.0):.4f}。</p>
  <p><strong>数据来源：</strong><code>{source_file}</code></p>
</section>
"""
    body_match = re.search(r"<body[^>]*>", html, flags=re.I)
    if body_match:
        html = html[: body_match.end()] + explanation + html[body_match.end() :]
    elif "</head>" in html.lower():
        idx = html.lower().find("</head>") + len("</head>")
        html = html[:idx] + explanation + html[idx:]
    else:
        html = explanation + html
    html_path.write_text(html, encoding="utf-8")


def inject_connectome_marker_labels(html_path: Path, labels: list[str]) -> None:
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
        json_end = html.find(";\n      var data = []", json_start)
        if json_end < 0:
            json_end = html.find(";\n\n      function", json_start)
        if json_end > json_start:
            try:
                payload = json.loads(html[json_start:json_end])
                connectome = payload.setdefault("connectome", {})
                connectome["marker_labels"] = labels
                connectome["marker_textposition"] = "top center"
                connectome["marker_text_size"] = 12
                connectome["marker_text_color"] = "#111111"
                html = html[:json_start] + json.dumps(payload, ensure_ascii=False) + html[json_end:]
            except Exception:
                pass
    html_path.write_text(html, encoding="utf-8")


def save_connectome_topview_svg(output_dir: Path, matrix: np.ndarray, coords: np.ndarray, name: str, stage_label: str, source_file: str, labels: list[str] | None = None, top_n: int = 35) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
        from nilearn import plotting
    except Exception as exc:
        raise RuntimeError(f"nilearn and matplotlib are required for projected connectome plotting: {exc}") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / f"{name}_connectome_topview.svg"
    plot_coords, _coordinate_space, _transform_file = connectome_plot_coords(coords, source_file)
    upper = matrix[np.triu_indices_from(matrix, k=1)]
    max_abs = float(np.max(np.abs(upper))) if upper.size else 1.0
    max_abs = max(max_abs, 1e-6)
    plt.rcParams["svg.fonttype"] = "none"
    red_blue_cmap = LinearSegmentedColormap.from_list(
        "continuous_blue_slate_red_connectome",
        [
            (0.0, "#0057ff"),
            (0.5, "#64748b"),
            (1.0, "#ff1f1f"),
        ],
        N=256,
    )
    fig = plt.figure(figsize=(8.5, 7.5), facecolor="white")
    title_ascii = stage_label.encode("ascii", "ignore").decode("ascii").strip(" /-") or name
    display = plotting.plot_connectome(
        matrix,
        plot_coords,
        node_color="#f2a51a",
        node_size=90,
        edge_cmap=red_blue_cmap,
        edge_vmin=-max_abs,
        edge_vmax=max_abs,
        edge_threshold=0.0,
        output_file=None,
        display_mode="z",
        figure=fig,
        title=f"{title_ascii} connectome (Nilearn)",
        annotate=True,
        black_bg=False,
        alpha=0.9,
        edge_kwargs={"linewidth": 4.5},
        node_kwargs={"linewidths": 1.5, "edgecolors": "white"},
        colorbar=True,
    )
    ax_obj = display.axes.get("z") or next(iter(display.axes.values()), None)
    if ax_obj is not None:
        projected = plot_coords[:, :2].T
        labels = labels or region_labels(coords)
        offsets = [(8, 8), (-8, 8), (8, -10), (-8, -10), (12, 0), (-12, 0)]
        for idx, (x, y) in enumerate(projected.T):
            dx, dy = offsets[idx % len(offsets)]
            text = ax_obj.ax.annotate(
                labels[idx],
                xy=(x, y),
                xytext=(dx, dy),
                textcoords="offset points",
                fontsize=8,
                fontweight="bold",
                color="#111111",
                ha="left" if dx >= 0 else "right",
                va="bottom" if dy >= 0 else "top",
                zorder=1000,
                bbox={"boxstyle": "round,pad=0.16", "facecolor": "white", "edgecolor": "none", "alpha": 0.78},
            )
    fig.savefig(str(svg_path), format="svg", bbox_inches="tight", facecolor="white")
    display.close()
    plt.close(fig)
    return str(svg_path)


def save_connectome_3d(output_dir: Path, matrix: np.ndarray, coords: np.ndarray, name: str, stage_label: str, source_file: str, labels: list[str] | None = None) -> dict[str, Any]:
    try:
        from nilearn import plotting
        from matplotlib.colors import LinearSegmentedColormap
    except Exception as exc:
        return {"connectome_3d_error": f"nilearn is required for 3D connectome plotting: {exc}"}
    html_path = output_dir / f"{name}_connectome_3d.html"
    summary = edge_summary(matrix)
    plot_coords, coordinate_space, transform_file = connectome_plot_coords(coords, source_file)
    red_blue_cmap = LinearSegmentedColormap.from_list(
        "continuous_blue_slate_red_connectome",
        [
            (0.0, "#0057ff"),
            (0.5, "#64748b"),
            (1.0, "#ff1f1f"),
        ],
        N=256,
    )
    view = plotting.view_connectome(
        matrix,
        plot_coords,
        edge_threshold=0.0,
        edge_cmap=red_blue_cmap,
        symmetric_cmap=True,
        linewidth=9.0,
        node_size=6.0,
        colorbar=True,
        title=f"{PARADIGM['name']} - {stage_label}",
    )
    view.save_as_html(str(html_path))
    inject_connectome_marker_labels(html_path, labels or region_labels(coords))
    inject_chinese_explanation(html_path, f"{PARADIGM['name']} - {stage_label}", summary, source_file, stage_label, coordinate_space, transform_file)
    return {
        "connectome_3d_html": str(html_path),
        "connectome_edge_summary": summary,
        "connectome_coordinate_space": coordinate_space,
        "connectome_coordinate_transform": transform_file,
        "connectome_coordinate_qc": latest_coordinate_qc(),
    }


def segment_output_label(path: Path) -> str:
    name = path.name.replace(".nii.gz", "")
    try:
        session = path.parents[3].name
        subject = path.parents[4].name
        return f"{subject}_{session}_{name}"
    except Exception:
        return name


def segment_stage_label(path: Path) -> str:
    name = path.name.replace(".nii.gz", "")
    if name.startswith("S_"):
        return f"Sleep {name}"
    if name.startswith("W_"):
        return f"Wake {name}"
    return name


def save_segment_connectomes(input_root: Path, output_dir: Path, subject: str | None, session: str | None) -> list[dict[str, Any]]:
    segment_files = find_segment_bold(input_root, subject, session)
    records: list[dict[str, Any]] = []
    segment_dir = output_dir / "sleep_wake_connectomes"
    for path in segment_files:
        try:
            ts, coords, meta = parcel_timeseries(path)
            matrix = corr_matrix(ts)
        except Exception as exc:
            records.append({"segment_file": str(path), "status": "failed", "reason": str(exc)})
            continue
        label = segment_output_label(path)
        stage_label = segment_stage_label(path)
        save_matrix(segment_dir / f"{label}_correlation_matrix.csv", matrix)
        plot_coords, coordinate_space, _transform_file = connectome_plot_coords(coords, str(path))
        roi_labels = meta.get("region_labels") if isinstance(meta.get("region_labels"), list) else None
        save_roi_coords(segment_dir / f"{label}_roi_coords.csv", coords, plot_coords, coordinate_space, roi_labels)
        connectome = save_connectome_3d(segment_dir, matrix, coords, label, stage_label, str(path), roi_labels)
        topview_svg = save_connectome_topview_svg(segment_dir, matrix, coords, label, stage_label, str(path), roi_labels)
        record = {
            "segment": label,
            "stage": "sleep" if path.name.startswith("S_") else "wake" if path.name.startswith("W_") else "",
            "stage_label": stage_label,
            "segment_file": str(path),
            "status": "completed",
            "correlation_matrix": str(segment_dir / f"{label}_correlation_matrix.csv"),
            "roi_coords": str(segment_dir / f"{label}_roi_coords.csv"),
            "connectome_topview_svg": topview_svg,
            **connectome,
        }
        record.update({"frame_count": meta.get("frame_count", 0), "parcel_count": meta.get("parcel_count", 0)})
        records.append(record)
    write_json(output_dir / "sleep_wake_connectomes.json", records)
    return records


def run_resting_state(input_root: Path, output_dir: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    bold_files = find_clean_bold(input_root, subject, session)
    if not bold_files:
        return unavailable("No clean BOLD NIfTI files found.", input_root, subject, session)
    ts, coords, meta = parcel_timeseries(bold_files[0])
    r = corr_matrix(ts)
    z = np.arctanh(np.clip(r, -0.999999, 0.999999))
    save_matrix(output_dir / "correlation_matrix.csv", r)
    save_matrix(output_dir / "fisher_z_matrix.csv", z)
    plot_coords, coordinate_space, _transform_file = connectome_plot_coords(coords, str(bold_files[0]))
    roi_labels = meta.get("region_labels") if isinstance(meta.get("region_labels"), list) else None
    save_roi_coords(output_dir / "roi_coords.csv", coords, plot_coords, coordinate_space, roi_labels)
    connectome_outputs = save_connectome_3d(output_dir, r, coords, "resting_state", "Full run / 全程", str(bold_files[0]), roi_labels)
    topview_svg = save_connectome_topview_svg(output_dir, r, coords, "resting_state", "Full run / 全程", str(bold_files[0]), roi_labels)
    segment_connectomes = save_segment_connectomes(input_root, output_dir, subject, session)
    upper = r[np.triu_indices_from(r, k=1)]
    result = base_result("completed", input_root, subject, session)
    result.update(meta)
    result.update(
        {
            "used_file": str(bold_files[0]),
            "metric_summary": {
                "mean_r": float(np.mean(upper)),
                "mean_abs_r": float(np.mean(np.abs(upper))),
                "max_abs_r": float(np.max(np.abs(upper))),
                "edge_count": int(upper.size),
            },
            "outputs": {
                "correlation_matrix": str(output_dir / "correlation_matrix.csv"),
                "fisher_z_matrix": str(output_dir / "fisher_z_matrix.csv"),
                "roi_coords": str(output_dir / "roi_coords.csv"),
                "sleep_wake_connectomes": str(output_dir / "sleep_wake_connectomes.json"),
                "sleep_wake_connectome_count": len([item for item in segment_connectomes if item.get("status") == "completed"]),
                "sleep_wake_connectome_html": [item.get("connectome_3d_html", "") for item in segment_connectomes if item.get("connectome_3d_html")],
                "sleep_wake_topview_svg": [item.get("connectome_topview_svg", "") for item in segment_connectomes if item.get("connectome_topview_svg")],
                "connectome_topview_svg": topview_svg,
                **connectome_outputs,
            },
        }
    )
    return result


def run_dynamic_fc(input_root: Path, output_dir: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    bold_files = find_clean_bold(input_root, subject, session)
    if not bold_files:
        return unavailable("No clean BOLD NIfTI files found.", input_root, subject, session)
    ts, coords, meta = parcel_timeseries(bold_files[0])
    frames = ts.shape[1]
    window = min(60, max(8, frames // 3))
    step = max(4, window // 4)
    rows = []
    vectors = []
    matrices = []
    for start in range(0, max(1, frames - window + 1), step):
        end = min(frames, start + window)
        if end - start < 6:
            continue
        r = corr_matrix(ts[:, start:end])
        vec = r[np.triu_indices_from(r, k=1)]
        matrices.append(r)
        vectors.append(vec)
        rows.append({"window_index": len(rows), "start_frame": start, "end_frame": end, "mean_abs_r": float(np.mean(np.abs(vec))), "mean_r": float(np.mean(vec))})
    write_csv(output_dir / "window_metrics.csv", rows)
    distances = []
    for prev, curr in zip(vectors, vectors[1:]):
        distances.append(float(np.linalg.norm(curr - prev) / math.sqrt(curr.size)))
    outputs = {"window_metrics": str(output_dir / "window_metrics.csv")}
    if matrices:
        mean_matrix = np.mean(np.stack(matrices), axis=0)
        save_matrix(output_dir / "mean_dynamic_correlation_matrix.csv", mean_matrix)
        plot_coords, coordinate_space, _transform_file = connectome_plot_coords(coords, str(bold_files[0]))
        roi_labels = meta.get("region_labels") if isinstance(meta.get("region_labels"), list) else None
        save_roi_coords(output_dir / "roi_coords.csv", coords, plot_coords, coordinate_space, roi_labels)
        outputs.update(
            {
                "mean_dynamic_correlation_matrix": str(output_dir / "mean_dynamic_correlation_matrix.csv"),
                "roi_coords": str(output_dir / "roi_coords.csv"),
                "connectome_topview_svg": save_connectome_topview_svg(output_dir, mean_matrix, coords, "dynamic_fc", "Dynamic FC mean / 动态功能连接均值", str(bold_files[0]), roi_labels),
                **save_connectome_3d(output_dir, mean_matrix, coords, "dynamic_fc", "Dynamic FC mean / 动态功能连接均值", str(bold_files[0]), roi_labels),
            }
        )
    result = base_result("completed" if rows else "not_executable", input_root, subject, session)
    result.update(meta)
    result.update(
        {
            "used_file": str(bold_files[0]),
            "window_count": len(rows),
            "window_size_frames": int(window),
            "step_frames": int(step),
            "metric_summary": {
                "mean_window_abs_r": float(np.mean([row["mean_abs_r"] for row in rows])) if rows else 0.0,
                "dynamic_variability": float(np.mean(distances)) if distances else 0.0,
            },
            "outputs": outputs,
        }
    )
    return result


def run_alff(input_root: Path, output_dir: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    bold_files = find_clean_bold(input_root, subject, session)
    if not bold_files:
        return unavailable("No clean BOLD NIfTI files found.", input_root, subject, session)
    ts, _coords, meta = parcel_timeseries(bold_files[0], parcel_count=20)
    tr = float(meta.get("tr", 2.0))
    freq = np.fft.rfftfreq(ts.shape[1], d=tr)
    amp = np.abs(np.fft.rfft(ts, axis=1))
    low = (freq >= 0.01) & (freq <= 0.08)
    total = (freq >= 0.01) & (freq <= min(0.25, 1.0 / (2.0 * tr)))
    alff = amp[:, low].mean(axis=1) if np.any(low) else np.zeros(ts.shape[0])
    total_amp = amp[:, total].mean(axis=1) if np.any(total) else np.ones(ts.shape[0])
    falff = np.divide(alff, total_amp, out=np.zeros_like(alff), where=total_amp > 0)
    rows = [{"parcel": i, "alff": float(a), "falff": float(f)} for i, (a, f) in enumerate(zip(alff, falff))]
    write_csv(output_dir / "alff_falff_summary.csv", rows)
    result = base_result("completed", input_root, subject, session)
    result.update(meta)
    result.update(
        {
            "used_file": str(bold_files[0]),
            "frequency_band_hz": [0.01, 0.08],
            "metric_summary": {
                "mean_alff": float(np.mean(alff)),
                "std_alff": float(np.std(alff)),
                "mean_falff": float(np.mean(falff)),
                "std_falff": float(np.std(falff)),
            },
            "outputs": {"alff_falff_summary": str(output_dir / "alff_falff_summary.csv")},
        }
    )
    return result


def run_sleep_stage(input_root: Path, output_dir: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    segment_files = find_segments(input_root, subject, session)
    if not segment_files:
        return unavailable("No segment/segment_summary.json files found.", input_root, subject, session)
    rows = []
    for path in segment_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.append({"segment_summary": str(path), "keys": ",".join(sorted(payload.keys())), "segment_count": len(payload.get("segments", [])) if isinstance(payload.get("segments"), list) else 0})
    write_csv(output_dir / "stage_summary.csv", rows)
    result = base_result("completed", input_root, subject, session)
    result.update({"segment_files": [str(p) for p in segment_files], "metric_summary": {"segment_file_count": len(segment_files), "total_declared_segments": sum(row["segment_count"] for row in rows)}, "outputs": {"stage_summary": str(output_dir / "stage_summary.csv")}})
    return result


def run_graph(input_root: Path, output_dir: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    base = run_resting_state(input_root, output_dir, subject, session)
    if base.get("status") != "completed":
        return base
    matrix = np.loadtxt(output_dir / "correlation_matrix.csv", delimiter=",")
    abs_matrix = np.abs(matrix)
    upper = abs_matrix[np.triu_indices_from(abs_matrix, k=1)]
    threshold = float(np.quantile(upper, 0.80)) if upper.size else 1.0
    adjacency = ((abs_matrix >= threshold) & (~np.eye(matrix.shape[0], dtype=bool))).astype(int)
    degree = adjacency.sum(axis=1)
    density = float(adjacency.sum() / max(1, matrix.shape[0] * (matrix.shape[0] - 1)))
    triangles = np.trace(np.linalg.matrix_power(adjacency, 3)) / 6.0 if matrix.shape[0] <= 80 else 0.0
    graph_metrics = {"node_count": int(matrix.shape[0]), "edge_density": density, "mean_degree": float(np.mean(degree)), "max_degree": int(np.max(degree)), "triangle_count": float(triangles), "threshold_abs_r": threshold}
    write_json(output_dir / "graph_metrics.json", graph_metrics)
    base["metric_summary"] = graph_metrics
    base["outputs"]["graph_metrics"] = str(output_dir / "graph_metrics.json")
    return base


def run_surface(input_root: Path, output_dir: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    files = find_surface_bold(input_root, subject, session)
    result = base_result("completed" if files else "not_executable", input_root, subject, session)
    result.update({"surface_file_count": len(files), "surface_files": [str(p) for p in files[:20]], "metric_summary": {"surface_file_count": len(files)}})
    if not files:
        result["reason"] = "No clean_data/surface/*.func.gii files found."
    return result


def run_task_glm(input_root: Path, output_dir: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    files = find_events(input_root, subject, session)
    rows = []
    for path in files:
        with path.open("r", encoding="utf-8") as f:
            header = f.readline().strip().split("\t")
            line_count = sum(1 for _ in f)
        rows.append({"events_file": str(path), "columns": ",".join(header), "event_count": line_count})
    if rows:
        write_csv(output_dir / "events_inventory.csv", rows)
    result = base_result("completed" if rows else "not_executable", input_root, subject, session)
    result.update({"event_files": [str(p) for p in files], "metric_summary": {"event_file_count": len(files), "event_count": sum(row["event_count"] for row in rows)}})
    if rows:
        result["outputs"] = {"events_inventory": str(output_dir / "events_inventory.csv")}
    else:
        result["reason"] = "No events.tsv files found."
    return result


def run_mvpa(input_root: Path, output_dir: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    result = run_task_glm(input_root, output_dir, subject, session)
    result["paradigm"] = PARADIGM["id"]
    result["name"] = PARADIGM["name"]
    if result.get("status") == "completed":
        result["status"] = "not_executable"
        result["reason"] = "Event files exist, but no explicit trial labels/classes were detected for decoding."
    return result


def find_by_patterns(input_root: Path, patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(path for path in sorted(input_root.glob(pattern)) if path.is_file())
    return sorted(set(files))


def summarize_numeric_table(path: Path, max_rows: int = 5000) -> dict[str, Any]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    rows = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        fieldnames = reader.fieldnames or []
        for idx, row in enumerate(reader):
            if idx >= max_rows:
                break
            rows.append(row)
    numeric: dict[str, list[float]] = {}
    for row in rows:
        for key, value in row.items():
            try:
                numeric.setdefault(key, []).append(float(value))
            except Exception:
                continue
    summary = {
        "file": str(path),
        "row_count_scanned": len(rows),
        "columns": fieldnames,
        "numeric_columns": sorted(numeric),
        "metrics": {},
    }
    for key, values in numeric.items():
        arr = np.asarray(values, dtype=float)
        if arr.size:
            summary["metrics"][key] = {
                "mean": float(np.nanmean(arr)),
                "std": float(np.nanstd(arr)),
                "min": float(np.nanmin(arr)),
                "max": float(np.nanmax(arr)),
                "count": int(arr.size),
            }
    return summary


def summarize_npy(path: Path) -> dict[str, Any]:
    arr = np.load(path, allow_pickle=False)
    numeric = np.asarray(arr, dtype=float) if np.issubdtype(arr.dtype, np.number) else np.asarray([])
    return {
        "file": str(path),
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
        "metrics": {
            "mean": float(np.nanmean(numeric)) if numeric.size else 0.0,
            "std": float(np.nanstd(numeric)) if numeric.size else 0.0,
            "min": float(np.nanmin(numeric)) if numeric.size else 0.0,
            "max": float(np.nanmax(numeric)) if numeric.size else 0.0,
        },
    }


def run_file_inventory_paradigm(input_root: Path, output_dir: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    pattern_map = {
        "eeg_meg_time_frequency": ["**/*.edf", "**/*.bdf", "**/*.set", "**/*.fif", "**/*eeg*.csv", "**/*eeg*.tsv", "**/*meg*.fif"],
        "erp_evoked_response": ["**/*.edf", "**/*.bdf", "**/*.set", "**/*.fif", "**/*events.tsv", "**/*events.csv"],
        "source_connectivity": ["**/*.fif", "**/*.edf", "**/*.set", "**/*connect*.csv"],
        "spike_train_statistics": ["**/*spike*.npy", "**/*spike*.csv", "**/*units*.tsv"],
        "lfp_spectral_coupling": ["**/*lfp*.npy", "**/*lfp*.csv", "**/*lfp*.mat"],
        "behavioral_computational_modeling": ["**/*behavior*.csv", "**/*behav*.csv", "**/*trial*.csv", "**/*task*.csv"],
        "eye_tracking_pupil_gaze": ["**/*eye*.csv", "**/*gaze*.csv", "**/*pupil*.csv", "**/*.asc"],
        "structural_morphometry": ["**/*_T1w.nii", "**/*_T1w.nii.gz", "**/*_T2w.nii", "**/*_T2w.nii.gz"],
        "diffusion_connectomics": ["**/*_dwi.nii", "**/*_dwi.nii.gz", "**/*.bvec", "**/*.bval"],
        "pet_neurochemistry": ["**/*pet*.nii", "**/*pet*.nii.gz", "**/*_pet.json"],
        "calcium_population_dynamics": ["**/*calcium*.npy", "**/*suite2p*/**/*.npy", "**/*caiman*/**/*.hdf5"],
        "neurogenomics_association": ["**/*rna*.csv", "**/*transcript*.tsv", "**/*gene*.csv", "**/*cell*.h5ad"],
        "multimodal_neuroscience_fusion": ["**/*.csv", "**/*.tsv", "**/*.json", "**/*.npy", "**/*.nii", "**/*.nii.gz", "**/*.edf", "**/*.fif"],
    }
    files = find_by_patterns(input_root, pattern_map.get(PARADIGM["id"], ["**/*"]))
    table_summaries = []
    array_summaries = []
    for path in files[:20]:
        suffix = path.suffix.lower()
        try:
            if suffix in {".csv", ".tsv"}:
                table_summaries.append(summarize_numeric_table(path))
            elif suffix == ".npy":
                array_summaries.append(summarize_npy(path))
        except Exception as exc:
            table_summaries.append({"file": str(path), "error": str(exc)})
    write_json(output_dir / "file_inventory.json", {"files": [str(p) for p in files[:200]]})
    if table_summaries:
        write_json(output_dir / "table_summaries.json", table_summaries)
    if array_summaries:
        write_json(output_dir / "array_summaries.json", array_summaries)
    status = "completed" if files else "not_executable"
    result = base_result(status, input_root, subject, session)
    result.update(
        {
            "file_count": len(files),
            "example_files": [str(p) for p in files[:20]],
            "metric_summary": {
                "file_count": len(files),
                "numeric_table_count": len(table_summaries),
                "array_count": len(array_summaries),
            },
            "outputs": {
                "file_inventory": str(output_dir / "file_inventory.json"),
                "table_summaries": str(output_dir / "table_summaries.json") if table_summaries else "",
                "array_summaries": str(output_dir / "array_summaries.json") if array_summaries else "",
            },
        }
    )
    if not files:
        result["reason"] = "No files matching this neuroscience paradigm were found."
    return result


def base_result(status: str, input_root: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    return {
        "paradigm": PARADIGM["id"],
        "name": PARADIGM["name"],
        "status": status,
        "input_root": str(input_root),
        "subject": subject or "",
        "session": session or "",
        "required_data": PARADIGM.get("required_data", []),
        "expected_outputs": PARADIGM.get("outputs", []),
    }


def unavailable(reason: str, input_root: Path, subject: str | None, session: str | None) -> dict[str, Any]:
    result = base_result("not_executable", input_root, subject, session)
    result["reason"] = reason
    return result

import argparse


class ExperimentContext:
    """保存一次实验执行的路径、被试、范式和中间结果。"""

    def __init__(self, input_root: Path, output_dir: Path, subject: str | None, session: str | None):
        self.input_root = input_root
        self.output_dir = output_dir
        self.subject = subject
        self.session = session
        self.result: dict[str, Any] = {}
        self.messages: list[str] = []

    def add_message(self, message: str) -> None:
        self.messages.append(message)

    def result_path(self) -> Path:
        return self.output_dir / f"{PARADIGM['id']}_result.json"

    def plan_path(self) -> Path:
        return self.output_dir / f"{PARADIGM['id']}_class_pipeline_plan_zh.json"

    def summary(self) -> dict[str, Any]:
        return {
            "paradigm": PARADIGM["id"],
            "status": self.result.get("status"),
            "result": str(self.result_path()),
            "messages": self.messages,
        }


class RuntimeSetupStep:
    """步骤 1：检查输入、配置缓存并创建输出目录。"""

    def validate_paths(self, context: ExperimentContext) -> None:
        if not context.input_root.exists():
            raise FileNotFoundError(f"输入目录不存在: {context.input_root}")

    def prepare_output_dir(self, context: ExperimentContext) -> None:
        context.output_dir.mkdir(parents=True, exist_ok=True)

    def prepare_runtime_cache(self) -> None:
        configure_runtime_cache()

    def describe_runtime(self, context: ExperimentContext) -> None:
        context.add_message(f"输入目录: {context.input_root}")
        context.add_message(f"输出目录: {context.output_dir}")
        if context.subject:
            context.add_message(f"被试: {context.subject}")
        if context.session:
            context.add_message(f"Session: {context.session}")

    def run(self, context: ExperimentContext) -> ExperimentContext:
        self.validate_paths(context)
        self.prepare_runtime_cache()
        self.prepare_output_dir(context)
        self.describe_runtime(context)
        return context


class ExperimentPlanStep:
    """步骤 2：写出中文实验计划，便于追溯创新点和范式绑定关系。"""

    def build_plan_payload(self, context: ExperimentContext) -> dict[str, Any]:
        return {
            **EXPERIMENT_PLAN,
            "runtime": {
                "input_root": str(context.input_root),
                "output_dir": str(context.output_dir),
                "subject": context.subject or "",
                "session": context.session or "",
            },
        }

    def write_plan(self, context: ExperimentContext, payload: dict[str, Any]) -> None:
        write_json(context.plan_path(), payload)

    def record_plan_message(self, context: ExperimentContext) -> None:
        context.add_message(f"已写出实验计划: {context.plan_path()}")

    def run(self, context: ExperimentContext) -> ExperimentContext:
        payload = self.build_plan_payload(context)
        self.write_plan(context, payload)
        self.record_plan_message(context)
        return context


class ParadigmRunnerStep:
    """步骤 3：执行当前范式对应的分析函数。"""

    def __init__(self) -> None:
        self.runner_registry = self.build_runner_registry()

    def build_runner_registry(self) -> dict[str, Any]:
        return {
            "resting_state_functional_connectivity": run_resting_state,
            "dynamic_functional_connectivity": run_dynamic_fc,
            "alff_falff_frequency": run_alff,
            "sleep_stage_analysis": run_sleep_stage,
            "graph_theory_connectomics": run_graph,
            "surface_based_analysis": run_surface,
            "task_glm": run_task_glm,
            "mvpa_decoding": run_mvpa,
            "eeg_meg_time_frequency": run_file_inventory_paradigm,
            "erp_evoked_response": run_file_inventory_paradigm,
            "source_connectivity": run_file_inventory_paradigm,
            "spike_train_statistics": run_file_inventory_paradigm,
            "lfp_spectral_coupling": run_file_inventory_paradigm,
            "behavioral_computational_modeling": run_file_inventory_paradigm,
            "eye_tracking_pupil_gaze": run_file_inventory_paradigm,
            "structural_morphometry": run_file_inventory_paradigm,
            "diffusion_connectomics": run_file_inventory_paradigm,
            "pet_neurochemistry": run_file_inventory_paradigm,
            "calcium_population_dynamics": run_file_inventory_paradigm,
            "neurogenomics_association": run_file_inventory_paradigm,
            "multimodal_neuroscience_fusion": run_file_inventory_paradigm,
        }

    def select_runner(self) -> Any | None:
        return self.runner_registry.get(PARADIGM["id"])

    def execute_runner(self, runner: Any, context: ExperimentContext) -> dict[str, Any]:
        return runner(context.input_root, context.output_dir, context.subject, context.session)

    def build_missing_runner_result(self, context: ExperimentContext) -> dict[str, Any]:
        return unavailable("No runner implemented for this paradigm.", context.input_root, context.subject, context.session)

    def normalize_result(self, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("paradigm", PARADIGM["id"])
        result.setdefault("name", PARADIGM["name"])
        result.setdefault("outputs", {})
        return result

    def record_runner_message(self, context: ExperimentContext) -> None:
        context.add_message(f"已执行范式 runner: {PARADIGM['id']}，状态={context.result.get('status')}")

    def run(self, context: ExperimentContext) -> ExperimentContext:
        runner = self.select_runner()
        if runner is None:
            context.result = self.build_missing_runner_result(context)
        else:
            context.result = self.execute_runner(runner, context)
        context.result = self.normalize_result(context.result)
        self.record_runner_message(context)
        return context


class ConnectomeValidationStep:
    """步骤 4：功能连接范式必须生成 3D connectome HTML 和俯视图。"""

    def requires_connectome(self) -> bool:
        return PARADIGM["id"] in {"resting_state_functional_connectivity", "dynamic_functional_connectivity"}

    def ensure_result_payload(self, context: ExperimentContext) -> dict[str, Any]:
        return context.result or {
            "status": "failed",
            "reason": "范式执行没有返回 result。",
            "outputs": {},
        }

    def validate_html(self, result: dict[str, Any], checks: list[str]) -> None:
        outputs = result.setdefault("outputs", {})
        html_path = outputs.get("connectome_3d_html", "")
        if html_path and Path(html_path).exists():
            checks.append(f"已生成 3D connectome HTML：{html_path}")
        else:
            result["status"] = "failed"
            result["reason"] = "功能连接实验未生成 3D connectome HTML。"
            checks.append("未找到 3D connectome HTML，需检查 nilearn/plotly 依赖、BOLD 数据和 ROI 坐标。")

    def validate_topview(self, result: dict[str, Any], checks: list[str]) -> None:
        outputs = result.setdefault("outputs", {})
        topview_path = outputs.get("connectome_topview_svg", "")
        if topview_path and Path(topview_path).exists():
            checks.append(f"已生成功能连接俯视图 SVG：{topview_path}")
        else:
            checks.append("未找到功能连接俯视图 SVG。")

    def attach_validation_summary(self, result: dict[str, Any], checks: list[str]) -> None:
        result["post_execution_checks_zh"] = checks

    def run(self, context: ExperimentContext) -> ExperimentContext:
        if not self.requires_connectome():
            context.add_message("当前范式不需要 3D connectome 强制校验。")
            return context
        result = self.ensure_result_payload(context)
        checks = list(result.get("post_execution_checks_zh", []))
        self.validate_html(result, checks)
        self.validate_topview(result, checks)
        self.attach_validation_summary(result, checks)
        context.result = result
        context.add_message("已完成 3D connectome 和俯视图校验。")
        return context


class ResultWriteStep:
    """步骤 5：写出 result.json，并在标准输出中返回执行摘要。"""

    def enrich_result(self, context: ExperimentContext) -> None:
        context.result.setdefault("pipeline_messages", context.messages)
        context.result.setdefault("experiment_plan", str(context.plan_path()))

    def write_result_json(self, context: ExperimentContext) -> None:
        write_json(context.result_path(), context.result)
        write_json(context.output_dir / "latest_result.json", context.result)

    def build_stdout_summary(self, context: ExperimentContext) -> dict[str, Any]:
        return context.summary()

    def emit_summary(self, summary: dict[str, Any]) -> None:
        print(json.dumps(summary, ensure_ascii=False))

    def run(self, context: ExperimentContext) -> ExperimentContext:
        self.enrich_result(context)
        self.write_result_json(context)
        self.emit_summary(self.build_stdout_summary(context))
        return context


class ExperimentPipeline:
    """按类组织的实验 pipeline，每一步都是独立类。"""

    def __init__(self) -> None:
        self.steps = self.build_steps()

    def build_steps(self) -> list[Any]:
        return [
            RuntimeSetupStep(),
            ExperimentPlanStep(),
            ParadigmRunnerStep(),
            ConnectomeValidationStep(),
            ResultWriteStep(),
        ]

    def run_step(self, step: Any, context: ExperimentContext) -> ExperimentContext:
        return step.run(context)

    def should_continue(self, context: ExperimentContext) -> bool:
        return True

    def run(self, context: ExperimentContext) -> dict[str, Any]:
        for step in self.steps:
            if not self.should_continue(context):
                break
            context = self.run_step(step, context)
        return context.result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one class-based neuroscience experiment.")
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--subject", default="")
    parser.add_argument("--session", default="")
    args = parser.parse_args()
    context = ExperimentContext(args.input_root, args.output_dir, args.subject or None, args.session or None)
    result = ExperimentPipeline().run(context)
    return 0 if result.get("status") in {"completed", "not_executable"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
