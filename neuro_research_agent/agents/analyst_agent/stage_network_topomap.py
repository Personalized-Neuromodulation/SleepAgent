from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle, Ellipse, Polygon


ROI_POSITIONS: dict[str, tuple[float, float]] = {
    "CorticalGM_L": (-0.55, 0.18),
    "CorticalGM_R": (0.55, 0.18),
    "CorticalGM_Bilateral": (0.00, 0.42),
    "Thalamus_L": (-0.22, 0.02),
    "Thalamus_R": (0.22, 0.02),
    "Thalamus_Bilateral": (0.00, 0.02),
    "Caudate": (0.00, 0.22),
    "Putamen": (-0.34, -0.12),
    "Pallidum": (0.34, -0.12),
    "Hippocampus": (-0.32, -0.48),
    "Amygdala": (0.32, -0.48),
    "Cerebellum": (0.00, -0.82),
    "BrainStem": (0.00, -0.60),
    "WhiteMatter_L": (-0.66, -0.18),
    "WhiteMatter_R": (0.66, -0.18),
    "WhiteMatter_Bilateral": (0.00, -0.25),
    "CSF": (0.00, 0.72),
}


def load_edges(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"segment", "stage", "start", "end", "frames", "roi_a", "roi_b", "r", "fisher_z"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns in {path}: {missing}")
    df["r"] = pd.to_numeric(df["r"], errors="coerce")
    df["fisher_z"] = pd.to_numeric(df["fisher_z"], errors="coerce")
    return df.dropna(subset=["r", "fisher_z"]).copy()


def aggregate_stage_edges(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby(["stage", "roi_a", "roi_b"], as_index=False)
        .agg(
            r=("r", "mean"),
            fisher_z=("fisher_z", "mean"),
            frames=("frames", "sum"),
            segment=("segment", "nunique"),
            start=("start", "min"),
            end=("end", "max"),
        )
        .rename(columns={"segment": "segment_count"})
    )
    grouped["segment"] = "stage_" + grouped["stage"].astype(str) + "_mean"
    return grouped


def _positions_for_rois(rois: list[str]) -> dict[str, tuple[float, float]]:
    known = {roi: ROI_POSITIONS[roi] for roi in rois if roi in ROI_POSITIONS}
    unknown = [roi for roi in rois if roi not in known]
    if unknown:
        radius = 0.88
        angles = np.linspace(0, 2 * np.pi, len(unknown), endpoint=False)
        for roi, angle in zip(unknown, angles):
            known[roi] = (float(radius * np.cos(angle)), float(radius * np.sin(angle)))
    return known


def _draw_head(ax: plt.Axes) -> None:
    ax.add_patch(Circle((0, 0), 1.0, facecolor="#f7f7f5", edgecolor="#1f2933", lw=1.6, zorder=0))
    ax.add_patch(Polygon([(-0.08, 0.99), (0.0, 1.13), (0.08, 0.99)], closed=False, fill=False, edgecolor="#1f2933", lw=1.4, zorder=1))
    ax.add_patch(Ellipse((-1.05, 0), 0.14, 0.34, facecolor="#f7f7f5", edgecolor="#1f2933", lw=1.2, zorder=1))
    ax.add_patch(Ellipse((1.05, 0), 0.14, 0.34, facecolor="#f7f7f5", edgecolor="#1f2933", lw=1.2, zorder=1))
    ax.set_xlim(-1.22, 1.22)
    ax.set_ylim(-1.16, 1.18)
    ax.set_aspect("equal")
    ax.axis("off")


def plot_topomap(
    edges: pd.DataFrame,
    out_file: Path,
    title: str,
    top_n: int = 35,
    min_abs_r: float = 0.0,
    use_fisher_z: bool = False,
) -> dict[str, Any]:
    metric = "fisher_z" if use_fisher_z else "r"
    plot_df = edges.copy()
    plot_df = plot_df[np.abs(plot_df[metric]) >= min_abs_r]
    plot_df = plot_df.sort_values(metric, key=lambda s: np.abs(s), ascending=False).head(top_n)
    rois = sorted(set(plot_df["roi_a"]) | set(plot_df["roi_b"]))
    positions = _positions_for_rois(rois)

    fig, ax = plt.subplots(figsize=(7.2, 7.6))
    _draw_head(ax)

    if not plot_df.empty:
        segments = []
        colors = []
        widths = []
        alphas = []
        max_abs = float(np.nanmax(np.abs(plot_df[metric]))) or 1.0
        for _, row in plot_df.iterrows():
            a = positions[row["roi_a"]]
            b = positions[row["roi_b"]]
            value = float(row[metric])
            segments.append([a, b])
            colors.append("#b2182b" if value >= 0 else "#2166ac")
            widths.append(0.8 + 4.2 * min(1.0, abs(value) / max_abs))
            alphas.append(0.25 + 0.65 * min(1.0, abs(value) / max_abs))
        line_collection = LineCollection(segments, colors=colors, linewidths=widths, zorder=2)
        line_collection.set_alpha(None)
        ax.add_collection(line_collection)
        for line, alpha in zip(line_collection.get_segments(), alphas):
            pass

    strength = {roi: 0.0 for roi in rois}
    signed_strength = {roi: 0.0 for roi in rois}
    for _, row in plot_df.iterrows():
        value = float(row[metric])
        strength[row["roi_a"]] += abs(value)
        strength[row["roi_b"]] += abs(value)
        signed_strength[row["roi_a"]] += value
        signed_strength[row["roi_b"]] += value
    max_strength = max(strength.values()) if strength else 1.0
    for roi in rois:
        x, y = positions[roi]
        signed = signed_strength[roi]
        size = 150 + 550 * (strength[roi] / max_strength if max_strength else 0)
        color = "#d73027" if signed >= 0 else "#4575b4"
        ax.scatter([x], [y], s=size, c=color, edgecolors="white", linewidths=1.2, zorder=3)
        ax.text(x, y - 0.075, roi.replace("_", "\n"), ha="center", va="top", fontsize=7.4, color="#111827", zorder=4)

    ax.text(-1.08, -1.10, "blue: negative FC", color="#2166ac", fontsize=9, ha="left")
    ax.text(0.36, -1.10, "red: positive FC", color="#b2182b", fontsize=9, ha="left")
    ax.set_title(title, fontsize=13, pad=14)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, format="svg", bbox_inches="tight")
    plt.close(fig)
    return {
        "path": str(out_file),
        "edge_count_plotted": int(len(plot_df)),
        "top_n": int(top_n),
        "min_abs_r": float(min_abs_r),
        "metric": metric,
    }


def plot_stage_network_topomaps(
    edges_csv: Path,
    out_dir: Path,
    top_n: int = 35,
    min_abs_r: float = 0.0,
    use_fisher_z: bool = False,
    include_segments: bool = True,
    include_stage_means: bool = True,
) -> dict[str, Any]:
    df = load_edges(edges_csv)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "input": str(edges_csv),
        "output_dir": str(out_dir),
        "top_n": top_n,
        "min_abs_r": min_abs_r,
        "use_fisher_z": use_fisher_z,
        "segment_plots": [],
        "stage_mean_plots": [],
    }

    if include_segments:
        for segment, segment_df in df.groupby("segment", sort=True):
            stage = str(segment_df["stage"].iloc[0])
            title = f"{segment} ({stage}) functional connectivity topomap"
            out_file = out_dir / f"{segment}_fc_topomap.svg"
            manifest["segment_plots"].append(plot_topomap(segment_df, out_file, title, top_n=top_n, min_abs_r=min_abs_r, use_fisher_z=use_fisher_z))

    if include_stage_means:
        stage_df = aggregate_stage_edges(df)
        for stage, single_stage_df in stage_df.groupby("stage", sort=True):
            title = f"Stage {stage} mean functional connectivity topomap"
            out_file = out_dir / f"stage_{stage}_mean_fc_topomap.svg"
            manifest["stage_mean_plots"].append(plot_topomap(single_stage_df, out_file, title, top_n=top_n, min_abs_r=min_abs_r, use_fisher_z=use_fisher_z))

    manifest_path = out_dir / "topomap_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest"] = str(manifest_path)
    return manifest
