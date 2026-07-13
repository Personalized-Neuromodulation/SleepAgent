#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import signal


LOW_BAND = (0.01, 0.08)
TOTAL_BAND = (0.01, 0.25)


def standard_bold_base(path: Path) -> str:
    name = path.name
    for suffix in (".nii.gz", ".nii"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    for marker in ("_12rp_50pca_csf_wm", "_desc-cleaned"):
        name = name.replace(marker, "")
    return name


def find_subject_dir(subject_root: Path, subject: str) -> tuple[Path, Path]:
    candidates = []
    for backend in ("fastsurfer", "freesurfer"):
        subjects_dir = subject_root / "fmriprep" / "output" / "sourcedata" / backend
        candidates.extend(sorted(path for path in subjects_dir.glob(f"{subject}*") if path.is_dir()))
    for subject_dir in candidates:
        if (subject_dir / "surf" / "lh.inflated").exists() and (subject_dir / "surf" / "rh.inflated").exists():
            return subject_dir.parent, subject_dir
    raise FileNotFoundError(f"未找到 {subject} 的 FastSurfer/FreeSurfer surface 目录")


def find_clean_bolds(subject_root: Path) -> list[Path]:
    return sorted(subject_root.glob("ses-*/clean_data/volume/*_desc-preproc_bold_12rp_50pca_csf_wm.nii.gz"))


def compute_alff_maps(clean_bold: Path, tr: float) -> tuple[Path, Path]:
    img = nib.load(str(clean_bold))
    data = np.asarray(img.dataobj, dtype=np.float32)
    if data.ndim != 4:
        raise ValueError(f"clean BOLD 不是 4D: {clean_bold}")
    n_tp = data.shape[-1]
    flat = data.reshape((-1, n_tp))
    finite = np.isfinite(flat).all(axis=1)
    variable = np.nanstd(flat, axis=1) > 0
    valid = finite & variable
    centered = np.zeros_like(flat, dtype=np.float32)
    centered[valid] = flat[valid] - flat[valid].mean(axis=1, keepdims=True)

    fs = 1.0 / tr
    nperseg = min(n_tp, max(8, min(128, n_tp)))
    freqs, psd = signal.welch(centered[valid], fs=fs, axis=1, nperseg=nperseg)
    low = (freqs >= LOW_BAND[0]) & (freqs <= LOW_BAND[1])
    total = (freqs >= TOTAL_BAND[0]) & (freqs <= TOTAL_BAND[1])

    alff_valid = np.sqrt(np.trapezoid(psd[:, low], freqs[low], axis=1)) if low.any() else np.full(valid.sum(), np.nan)
    denom = np.sqrt(np.trapezoid(psd[:, total], freqs[total], axis=1)) if total.any() else np.full(valid.sum(), np.nan)
    falff_valid = np.divide(alff_valid, denom, out=np.full_like(alff_valid, np.nan), where=denom > 0)

    alff = np.full(flat.shape[0], np.nan, dtype=np.float32)
    falff = np.full(flat.shape[0], np.nan, dtype=np.float32)
    alff[valid] = alff_valid.astype(np.float32)
    falff[valid] = falff_valid.astype(np.float32)

    session = clean_bold.parents[2].name
    out_dir = clean_bold.parents[2] / "time_frequency" / "surface_maps"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = standard_bold_base(clean_bold)
    alff_path = out_dir / f"{base}_desc-ALFF_map.nii.gz"
    falff_path = out_dir / f"{base}_desc-fALFF_map.nii.gz"
    nib.save(nib.Nifti1Image(alff.reshape(data.shape[:3]), img.affine, img.header), str(alff_path))
    nib.save(nib.Nifti1Image(falff.reshape(data.shape[:3]), img.affine, img.header), str(falff_path))
    meta = {
        "session": session,
        "source_clean_bold": str(clean_bold),
        "TR": tr,
        "low_band_hz": LOW_BAND,
        "total_band_hz": TOTAL_BAND,
        "alff_map": str(alff_path),
        "falff_map": str(falff_path),
    }
    (out_dir / f"{base}_desc-alffFalffSurfaceMaps.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return alff_path, falff_path


def vol2surf(src: Path, subjects_dir: Path, subject: str, hemi: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SUBJECTS_DIR"] = str(subjects_dir)
    cmd = [
        "mri_vol2surf",
        "--src",
        str(src),
        "--out",
        str(out),
        "--out_type",
        "mgh",
        "--regheader",
        subject,
        "--hemi",
        hemi,
        "--surf",
        "white",
        "--projfrac-avg",
        "0",
        "1",
        "0.2",
    ]
    subprocess.run(cmd, check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def load_surface_values(path: Path) -> np.ndarray:
    data = np.asarray(nib.load(str(path)).get_fdata()).squeeze()
    return data.astype(np.float32)


def read_cortex_mask(subject_dir: Path, hemi: str, n_vertices: int) -> np.ndarray:
    mask = np.zeros(n_vertices, dtype=bool)
    label_path = subject_dir / "label" / f"{hemi}.cortex.label"
    if label_path.exists():
        label = nib.freesurfer.read_label(str(label_path))
        mask[label[label < n_vertices]] = True
        return mask
    return np.ones(n_vertices, dtype=bool)


def smooth_surface_values(values: np.ndarray, faces: np.ndarray, mask: np.ndarray, iterations: int = 16) -> np.ndarray:
    values = values.astype(np.float64, copy=True)
    valid = mask & np.isfinite(values)
    if not np.any(valid):
        return np.full_like(values, np.nan, dtype=np.float32)
    fill = float(np.nanmedian(values[valid]))
    values[~valid] = fill

    edges = np.vstack(
        (
            faces[:, [0, 1]],
            faces[:, [1, 2]],
            faces[:, [2, 0]],
            faces[:, [1, 0]],
            faces[:, [2, 1]],
            faces[:, [0, 2]],
        )
    )
    src = edges[:, 0]
    dst = edges[:, 1]
    edge_ok = mask[src] & mask[dst]
    src = src[edge_ok]
    dst = dst[edge_ok]
    degree = np.bincount(dst, minlength=values.shape[0]).astype(np.float64)

    for _ in range(iterations):
        acc = np.zeros_like(values)
        np.add.at(acc, dst, values[src])
        neigh = np.divide(acc, degree, out=values.copy(), where=degree > 0)
        values[mask] = 0.58 * values[mask] + 0.42 * neigh[mask]
    values[~mask] = np.nan
    return values.astype(np.float32)


def robust_limits(values: list[np.ndarray], metric: str) -> tuple[float, float]:
    merged = np.concatenate([v[np.isfinite(v)] for v in values if np.isfinite(v).any()])
    if merged.size == 0:
        return 0.0, 1.0
    if metric == "ALFF":
        lo, hi = np.nanpercentile(merged, [5, 97.5])
    else:
        lo, hi = np.nanpercentile(merged, [2.5, 97.5])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo, hi = float(np.nanmin(merged)), float(np.nanmax(merged))
    return float(lo), float(hi)


def projected_coords(coords: np.ndarray, hemi: str) -> tuple[np.ndarray, np.ndarray]:
    x = -coords[:, 1] if hemi == "lh" else coords[:, 1]
    y = coords[:, 2]
    return x, y


def plot_svg(subject_dir: Path, maps: dict[str, dict[str, Path]], out_svg: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    fig, axes = plt.subplots(2, 2, figsize=(12.8, 8.0), constrained_layout=True)
    fig.patch.set_facecolor("white")
    prepared: dict[str, dict[str, dict[str, np.ndarray]]] = {"ALFF": {}, "fALFF": {}}

    for hemi in ("lh", "rh"):
        coords, faces = nib.freesurfer.read_geometry(str(subject_dir / "surf" / f"{hemi}.inflated"))
        cortex = read_cortex_mask(subject_dir, hemi, coords.shape[0])
        face_mask = ~np.all(cortex[faces], axis=1)
        x, y = projected_coords(coords, hemi)
        triang = mtri.Triangulation(x, y, triangles=faces)
        triang.set_mask(face_mask)
        sulc_path = subject_dir / "surf" / f"{hemi}.sulc"
        if sulc_path.exists():
            sulc = nib.freesurfer.read_morph_data(str(sulc_path)).astype(np.float32)
            sulc = np.clip(sulc, *np.nanpercentile(sulc[cortex], [2, 98]))
            sulc = (sulc - np.nanmin(sulc[cortex])) / (np.nanmax(sulc[cortex]) - np.nanmin(sulc[cortex]) + 1e-8)
            sulc = 0.82 + 0.18 * sulc
        else:
            sulc = np.full(coords.shape[0], 0.9, dtype=np.float32)
        for metric in ("ALFF", "fALFF"):
            raw = load_surface_values(maps[metric][hemi])
            valid = cortex & np.isfinite(raw)
            if np.any(valid):
                lo, hi = np.nanpercentile(raw[valid], [1, 99])
                raw = np.clip(raw, lo, hi)
            smoothed = smooth_surface_values(raw, faces, cortex, iterations=18 if metric == "ALFF" else 16)
            prepared[metric][hemi] = {
                "triang": triang,
                "values": smoothed,
                "sulc": sulc,
                "x": x,
                "y": y,
            }

    for row, metric in enumerate(("ALFF", "fALFF")):
        vmin, vmax = robust_limits([prepared[metric][hemi]["values"] for hemi in ("lh", "rh")], metric)
        for col, hemi in enumerate(("lh", "rh")):
            ax = axes[row, col]
            item = prepared[metric][hemi]
            ax.tripcolor(
                item["triang"],
                item["sulc"],
                cmap="Greys",
                shading="gouraud",
                vmin=0.70,
                vmax=1.05,
                alpha=0.34,
                rasterized=True,
            )
            sc = ax.tripcolor(
                item["triang"],
                item["values"],
                cmap="inferno" if metric == "ALFF" else "viridis",
                shading="gouraud",
                vmin=vmin,
                vmax=vmax,
                alpha=0.94,
                rasterized=True,
            )
            ax.set_title(f"{metric} {hemi.upper()}", fontsize=11, fontweight="medium", pad=4)
            ax.set_aspect("equal")
            ax.axis("off")
            ax.margins(0.02)
            cbar = fig.colorbar(sc, ax=ax, fraction=0.026, pad=0.006, aspect=28)
            cbar.outline.set_linewidth(0.4)
            cbar.ax.tick_params(labelsize=7, width=0.4, length=2.0)
    fig.suptitle(title, fontsize=13, fontweight="semibold", y=0.995)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_svg, format="svg", dpi=300, facecolor="white", bbox_inches="tight")
    fig.savefig(out_svg.with_suffix(".png"), format="png", dpi=360, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def process_subject(subject_root: Path, subject: str, tr: float) -> list[Path]:
    subjects_dir, subject_dir = find_subject_dir(subject_root, subject)
    outputs = []
    for clean_bold in find_clean_bolds(subject_root):
        base = standard_bold_base(clean_bold)
        session = clean_bold.parents[2].name
        out_dir = subject_root / session / "time_frequency" / "surface_maps"
        alff_nii, falff_nii = compute_alff_maps(clean_bold, tr)
        surface_maps = {"ALFF": {}, "fALFF": {}}
        for metric, src in (("ALFF", alff_nii), ("fALFF", falff_nii)):
            for hemi in ("lh", "rh"):
                out = out_dir / f"{base}_hemi-{hemi}_desc-{metric}_surf.mgh"
                vol2surf(src, subjects_dir, subject, hemi, out)
                surface_maps[metric][hemi] = out
        svg = out_dir / f"{base}_desc-alffFalffSurfaceMaps.svg"
        plot_svg(subject_dir, surface_maps, svg, f"{subject} {session} ALFF/fALFF surface maps")
        outputs.append(svg)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ALFF/fALFF volume maps and FastSurfer surface-map SVGs from existing clean BOLD.")
    parser.add_argument("--subject-root", required=True, type=Path)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--tr", type=float, default=2.0)
    args = parser.parse_args()
    outputs = process_subject(args.subject_root.resolve(), args.subject, args.tr)
    print(f"SURFACE_ALFF_FALFF_READY maps={len(outputs)}")
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
