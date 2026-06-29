from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import pandas as pd


def plot_paradigm_scores(evaluations: list[dict[str, Any]], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(evaluations)
    artifacts: dict[str, str] = {}
    if df.empty:
        return artifacts
    fig, ax = plt.subplots(figsize=(11, 5))
    x_positions = list(range(len(df)))
    ax.bar(x_positions, df["score_total"], color=["#2b6cb0" if x else "#8a8f98" for x in df["executable"]])
    ax.set_xticks(x_positions, labels=df["id"], rotation=35, ha="right", rotation_mode="anchor")
    ax.set_ylabel("Score")
    ax.set_ylim(0, 100)
    ax.set_title("Paradigm evaluation scores")
    ax.tick_params(axis="x", labelsize=9)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    score_path = out_dir / "paradigm_scores.svg"
    fig.savefig(score_path)
    plt.close(fig)
    artifacts["score_bar_svg"] = str(score_path)

    metric_cols = ["literature_score", "data_score", "code_score", "feasibility_score", "novelty_score"]
    heat = df.set_index("id")[metric_cols]
    fig, ax = plt.subplots(figsize=(9, max(3, 0.45 * len(heat))))
    im = ax.imshow(heat.to_numpy(), cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(metric_cols)), labels=metric_cols, rotation=25, ha="right")
    ax.set_yticks(range(len(heat.index)), labels=heat.index)
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Paradigm scoring components")
    fig.tight_layout()
    heat_path = out_dir / "paradigm_score_heatmap.svg"
    fig.savefig(heat_path)
    plt.close(fig)
    artifacts["score_heatmap_svg"] = str(heat_path)
    return artifacts


def collect_connectome_figures(execution_results: list[dict[str, Any]]) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for execution in execution_results:
        result_json = execution.get("result_json")
        if not result_json:
            continue
        path = Path(result_json)
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        outputs = payload.get("outputs", {})
        prefix_parts = []
        if execution.get("innovation_id"):
            prefix_parts.append(str(execution.get("innovation_id")))
        prefix_parts.append(str(payload.get("paradigm", execution.get("paradigm", "connectome"))))
        artifact_prefix = "_".join(prefix_parts)
        connectome_html = outputs.get("connectome_3d_html")
        if connectome_html:
            artifacts[f"{artifact_prefix}_3d_connectome_html"] = connectome_html
        topview_svg = outputs.get("connectome_topview_svg")
        if topview_svg:
            artifacts[f"{artifact_prefix}_topview_connectome_svg"] = topview_svg
        for idx, segment_html in enumerate(outputs.get("sleep_wake_connectome_html", []), start=1):
            if segment_html:
                artifacts[f"{artifact_prefix}_sleep_wake_3d_connectome_{idx:03d}_html"] = segment_html
        for idx, segment_svg in enumerate(outputs.get("sleep_wake_topview_svg", []), start=1):
            if segment_svg:
                artifacts[f"{artifact_prefix}_sleep_wake_topview_connectome_{idx:03d}_svg"] = segment_svg
    return artifacts
