from __future__ import annotations

from html import escape
import os
from pathlib import Path
import shutil
import textwrap
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import auc, roc_curve

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.experiment.agents.analysis_templates import load_analysis_table
from sleep_ai_scientist.schemas.experiment import ExperimentResultBundle, StatisticalTestResult


def render_experiment_visualizations(bundles: list[ExperimentResultBundle], output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    figures_dir = output / "figures"
    if figures_dir.exists():
        shutil.rmtree(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    figures: list[str] = []
    dashboard = {"plans": [_bundle_dashboard(bundle) for bundle in bundles]}

    matrix = _plot_primary_test_matrix(bundles, figures_dir)
    if matrix:
        figures.append(str(matrix))

    for bundle in bundles:
        for test in bundle.stats_result.tests if bundle.stats_result else []:
            model_fig = _plot_model_specific_result(bundle, test, figures_dir)
            if model_fig:
                figures.append(str(model_fig))

        robustness = _plot_robustness(bundle, figures_dir)
        if robustness:
            figures.append(str(robustness))

        negative_controls = _plot_negative_controls(bundle, figures_dir)
        if negative_controls:
            figures.append(str(negative_controls))

        missingness = _plot_missingness(bundle, figures_dir)
        if missingness:
            figures.append(str(missingness))

        ml_importance = _plot_ml_feature_importance(bundle, figures_dir)
        if ml_importance:
            figures.append(str(ml_importance))
        for ml_diagnostic in _plot_ml_diagnostics(bundle, figures_dir):
            figures.append(str(ml_diagnostic))

    html_path = output / "index.html"
    manifest_path = output / "visualization_manifest.json"
    figure_records = _build_figure_records(figures, bundles)
    manifest = {
        "html": str(html_path),
        "manifest": str(manifest_path),
        "figures": figures,
        "figure_records": figure_records,
        "dashboard": dashboard,
    }
    write_json(manifest_path, manifest)
    _write_html(html_path, bundles, figure_records, output)
    return manifest


def _bundle_dashboard(bundle: ExperimentResultBundle) -> dict[str, Any]:
    tests = bundle.stats_result.tests if bundle.stats_result else []
    passed = sum(1 for test in tests if test.passed)
    return {
        "plan_id": bundle.plan.plan_id,
        "hypothesis_id": bundle.plan.hypothesis_id,
        "hypothesis_title": bundle.plan.hypothesis_title,
        "primary_tests_passed": passed,
        "primary_tests_total": len(tests),
        "models": sorted({test.method for test in tests}),
        "ml_model": bundle.ml_result.model_type if bundle.ml_result else "",
        "predictors": list(bundle.plan.predictors),
        "outcomes": list(bundle.plan.outcomes),
        "negative_controls": list(bundle.plan.negative_controls),
    }


def _plot_primary_test_matrix(bundles: list[ExperimentResultBundle], figures_dir: Path) -> Path | None:
    tests = [test for bundle in bundles if bundle.stats_result for test in bundle.stats_result.tests]
    if not tests:
        return None
    rows = sorted({test.predictor for test in tests})
    cols = sorted({test.outcome for test in tests})
    values = pd.DataFrame(0.0, index=rows, columns=cols)
    labels = pd.DataFrame("", index=rows, columns=cols)
    for test in tests:
        values.loc[test.predictor, test.outcome] = float(test.effect or 0.0)
        labels.loc[test.predictor, test.outcome] = f"{test.effect:.2f}\np={test.p_value:.3g}" if test.effect is not None and test.p_value is not None else "NA"

    width = max(7.5, len(cols) * 2.8 + 2.8)
    height = max(5.0, len(rows) * 1.4 + 1.5)
    fig, ax = plt.subplots(figsize=(width, height), constrained_layout=True)
    image = ax.imshow(values.values, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)), [_wrap_label(_display_label(col), 18) for col in cols], rotation=25, ha="right")
    ax.set_yticks(range(len(rows)), [_wrap_label(_display_label(row), 22) for row in rows])
    ax.set_title("Primary Test Matrix\nEffect size and p-value by predictor/outcome", pad=14)
    for row_idx, row in enumerate(rows):
        for col_idx, col in enumerate(cols):
            ax.text(col_idx, row_idx, labels.loc[row, col], ha="center", va="center", fontsize=9)
    fig.colorbar(image, ax=ax, label="effect", fraction=0.046, pad=0.04)
    return _save(fig, figures_dir / "primary_test_matrix.png")


def _plot_model_specific_result(bundle: ExperimentResultBundle, test: StatisticalTestResult, figures_dir: Path) -> Path | None:
    if test.method == "linear_regression":
        return _plot_linear_regression(bundle, test, figures_dir)
    if test.method == "mixed_effects":
        return _plot_coefficient_terms(bundle, test, figures_dir, "mixed_effects_fixed_effects")
    return _plot_spearman(bundle, test, figures_dir)


def _plot_spearman(bundle: ExperimentResultBundle, test: StatisticalTestResult, figures_dir: Path) -> Path | None:
    clean = _test_table(bundle, test)
    if clean.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.2, 4.6), constrained_layout=True)
    ax.scatter(clean[test.predictor], clean[test.outcome], color="#2563eb", alpha=0.78)
    ax.set_title(_wrap_title(f"Spearman: {_display_label(test.predictor)} -> {_display_label(test.outcome)}"), pad=12)
    ax.set_xlabel(_wrap_label(_display_label(test.predictor), 26))
    ax.set_ylabel(_wrap_label(_display_label(test.outcome), 26))
    ax.text(0.02, 0.98, _stat_label(test), transform=ax.transAxes, va="top", fontsize=8)
    return _save(fig, figures_dir / f"spearman_scatter_{_safe(test.test_id)}.png")


def _plot_linear_regression(bundle: ExperimentResultBundle, test: StatisticalTestResult, figures_dir: Path) -> Path | None:
    clean = _test_table(bundle, test)
    if clean.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.2, 4.6), constrained_layout=True)
    x = clean[test.predictor]
    y = clean[test.outcome]
    ax.scatter(x, y, color="#0f766e", alpha=0.78)
    if len(clean) >= 2:
        slope, intercept = pd.Series(x).cov(pd.Series(y)) / pd.Series(x).var(), y.mean() - (pd.Series(x).cov(pd.Series(y)) / pd.Series(x).var()) * x.mean()
        ordered = x.sort_values()
        ax.plot(ordered, intercept + slope * ordered, color="#b91c1c", linewidth=1.8)
    ax.set_title(_wrap_title(f"Linear Regression: {_display_label(test.predictor)} -> {_display_label(test.outcome)}"), pad=12)
    ax.set_xlabel(_wrap_label(_display_label(test.predictor), 26))
    ax.set_ylabel(_wrap_label(_display_label(test.outcome), 26))
    ax.text(0.02, 0.98, _stat_label(test), transform=ax.transAxes, va="top", fontsize=8)
    return _save(fig, figures_dir / f"linear_regression_fit_{_safe(test.test_id)}.png")


def _plot_coefficient_terms(bundle: ExperimentResultBundle, test: StatisticalTestResult, figures_dir: Path, prefix: str) -> Path | None:
    terms = test.metadata.get("fixed_effects") or test.metadata.get("coefficients") or {}
    if not terms:
        return None
    labels = list(terms)
    values = [float(terms[label]) for label in labels]
    fig, ax = plt.subplots(figsize=(max(5, len(labels) * 1.2), 3.8))
    ax.bar(labels, values, color="#7c3aed")
    ax.axhline(0, color="#111827", linewidth=0.8)
    ax.set_title(f"{test.method} coefficients")
    ax.tick_params(axis="x", rotation=30)
    return _save(fig, figures_dir / f"{prefix}_{_safe(test.test_id)}.png")


def _plot_robustness(bundle: ExperimentResultBundle, figures_dir: Path) -> Path | None:
    checks = bundle.robustness_results
    if not checks:
        return None
    labels = [_test_pair_label(bundle, item.target_test_id) for item in checks]
    values = [item.sign_stability or 0.0 for item in checks]
    fig, ax = plt.subplots(figsize=(max(6.0, len(labels) * 1.8), 4.3), constrained_layout=True)
    ax.bar(range(len(labels)), values, color="#0891b2")
    ax.set_xticks(range(len(labels)), [_wrap_label(label, 18) for label in labels], rotation=25, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Sign stability")
    ax.set_title("Bootstrap Sign Stability\nHigher values indicate more stable effect direction", pad=12)
    return _save(fig, figures_dir / f"robustness_bootstrap_{_safe(bundle.plan.plan_id)}.png")


def _plot_negative_controls(bundle: ExperimentResultBundle, figures_dir: Path) -> Path | None:
    controls = bundle.negative_control_results
    if not controls:
        return None
    labels = [f"{_display_label(item.predictor)} -> {_display_label(item.outcome)}" for item in controls]
    values = [item.effect or 0.0 for item in controls]
    colors = ["#16a34a" if item.passed else "#dc2626" for item in controls]
    fig, ax = plt.subplots(figsize=(max(6.0, len(labels) * 1.9), 4.4), constrained_layout=True)
    ax.bar(range(len(labels)), values, color=colors)
    ax.axhline(0, color="#111827", linewidth=0.8)
    ax.set_xticks(range(len(labels)), [_wrap_label(label, 20) for label in labels], rotation=25, ha="right")
    ax.set_ylabel("Effect")
    ax.set_title("Negative Controls\nGreen=passed, red=failed", pad=12)
    for index, item in enumerate(controls):
        value = item.effect or 0.0
        va = "bottom" if value >= 0 else "top"
        offset = 0.015 if value >= 0 else -0.015
        ax.text(index, value + offset, f"{'pass' if item.passed else 'fail'}\ne={value:.2g}", ha="center", va=va, fontsize=8)
    low = min(0.0, *values)
    high = max(0.0, *values)
    span = high - low or 1.0
    ax.set_ylim(low - span * 0.28, high + span * 0.28)
    passed = plt.Rectangle((0, 0), 1, 1, color="#16a34a")
    failed = plt.Rectangle((0, 0), 1, 1, color="#dc2626")
    ax.legend([passed, failed], ["passed negative control", "failed negative control"], fontsize=8, loc="best")
    return _save(fig, figures_dir / f"negative_controls_{_safe(bundle.plan.plan_id)}.png")


def _plot_missingness(bundle: ExperimentResultBundle, figures_dir: Path) -> Path | None:
    variables = bundle.plan.variables
    if not variables:
        return None
    labels = [_display_label(variable.name) for variable in variables]
    values = [float(variable.missing_rate or 0.0) for variable in variables]
    fig, ax = plt.subplots(figsize=(max(6.0, len(labels) * 1.0), 4.1), constrained_layout=True)
    ax.bar(range(len(labels)), values, color="#f59e0b")
    ax.set_xticks(range(len(labels)), [_wrap_label(label, 18) for label in labels], rotation=25, ha="right")
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Missing rate")
    ax.set_title("Variable Missingness")
    return _save(fig, figures_dir / f"missingness_{_safe(bundle.plan.plan_id)}.png")


def _plot_ml_feature_importance(bundle: ExperimentResultBundle, figures_dir: Path) -> Path | None:
    result = bundle.ml_result
    if not result or not result.feature_importance:
        return None
    labels = list(result.feature_importance)
    values = [result.feature_importance[label] for label in labels]
    fig, ax = plt.subplots(figsize=(max(5, len(labels) * 1.1), 3.8))
    ax.bar(labels, values, color="#4f46e5")
    ax.set_title(f"ML Feature Importance: {result.model_type}")
    ax.tick_params(axis="x", rotation=30)
    return _save(fig, figures_dir / f"ml_feature_importance_{_safe(bundle.plan.plan_id)}.png")


def _plot_ml_diagnostics(bundle: ExperimentResultBundle, figures_dir: Path) -> list[Path]:
    result = bundle.ml_result
    if not result:
        return []
    task_type = str(result.metadata.get("task_type", ""))
    models = result.metadata.get("models", {})
    if not isinstance(models, dict):
        return []
    figures: list[Path] = []
    if task_type == "classification":
        confusion = _plot_ml_classification_confusion(bundle, models, figures_dir)
        if confusion:
            figures.append(confusion)
        roc = _plot_ml_classification_roc(bundle, models, figures_dir)
        if roc:
            figures.append(roc)
    elif task_type == "regression":
        pred = _plot_ml_regression_predictions(bundle, models, figures_dir)
        if pred:
            figures.append(pred)
    return figures


def _plot_ml_classification_confusion(bundle: ExperimentResultBundle, models: dict[str, Any], figures_dir: Path) -> Path | None:
    usable = [(name, payload) for name, payload in models.items() if isinstance(payload, dict) and payload.get("confusion_matrix")]
    if not usable:
        return None
    cols = len(usable)
    fig, axes = plt.subplots(1, cols, figsize=(max(4, cols * 3.2), 3.2), squeeze=False)
    for ax, (name, payload) in zip(axes[0], usable, strict=False):
        matrix = pd.DataFrame(payload["confusion_matrix"])
        image = ax.imshow(matrix.values, cmap="Blues")
        ax.set_title(_short(name, 22))
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Observed")
        for row in range(matrix.shape[0]):
            for col in range(matrix.shape[1]):
                ax.text(col, row, str(matrix.iloc[row, col]), ha="center", va="center", fontsize=9)
        fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    return _save(fig, figures_dir / f"ml_classification_confusion_{_safe(bundle.plan.plan_id)}.png")


def _plot_ml_classification_roc(bundle: ExperimentResultBundle, models: dict[str, Any], figures_dir: Path) -> Path | None:
    usable = [
        (name, payload)
        for name, payload in models.items()
        if isinstance(payload, dict) and payload.get("probabilities") and payload.get("observed")
    ]
    if not usable:
        return None
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    for name, payload in usable:
        y = payload["observed"]
        probabilities = payload["probabilities"]
        if len(set(y)) < 2:
            continue
        fpr, tpr, _ = roc_curve(y, probabilities)
        ax.plot(fpr, tpr, linewidth=1.5, label=f"{_short(name, 18)} AUC={auc(fpr, tpr):.2f}")
    ax.plot([0, 1], [0, 1], color="#6b7280", linestyle="--", linewidth=1)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ML Classification ROC")
    ax.legend(fontsize=8)
    return _save(fig, figures_dir / f"ml_classification_roc_{_safe(bundle.plan.plan_id)}.png")


def _plot_ml_regression_predictions(bundle: ExperimentResultBundle, models: dict[str, Any], figures_dir: Path) -> Path | None:
    usable = [
        (name, payload)
        for name, payload in models.items()
        if isinstance(payload, dict) and payload.get("predictions") and payload.get("observed")
    ]
    if not usable:
        return None
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    for name, payload in usable:
        ax.scatter(payload["observed"], payload["predictions"], alpha=0.7, label=_short(name, 18))
    values = [value for _, payload in usable for value in [*payload["observed"], *payload["predictions"]]]
    if values:
        lo, hi = min(values), max(values)
        ax.plot([lo, hi], [lo, hi], color="#111827", linestyle="--", linewidth=1)
    ax.set_xlabel("Observed")
    ax.set_ylabel("Predicted")
    ax.set_title("ML Regression Predicted vs Observed")
    ax.legend(fontsize=8)
    return _save(fig, figures_dir / f"ml_regression_predicted_observed_{_safe(bundle.plan.plan_id)}.png")


def _test_table(bundle: ExperimentResultBundle, test: StatisticalTestResult) -> pd.DataFrame:
    table = load_analysis_table(bundle.plan, {test.predictor, test.outcome})
    if table.empty or test.predictor not in table.columns or test.outcome not in table.columns:
        return pd.DataFrame()
    clean = table[[test.predictor, test.outcome]].copy()
    clean[test.predictor] = pd.to_numeric(clean[test.predictor], errors="coerce")
    clean[test.outcome] = pd.to_numeric(clean[test.outcome], errors="coerce")
    return clean.dropna()


def _build_figure_records(figures: list[str], bundles: list[ExperimentResultBundle]) -> list[dict[str, str]]:
    records = []
    for figure in figures:
        figure_path = Path(figure)
        kind, title, caption = _figure_metadata(figure_path, bundles)
        records.append(
            {
                "path": str(figure_path),
                "kind": kind,
                "title": title,
                "caption": caption,
            }
        )
    return records


def _figure_metadata(path: Path, bundles: list[ExperimentResultBundle]) -> tuple[str, str, str]:
    name = path.name
    if name == "primary_test_matrix.png":
        return (
            "primary_test_matrix",
            "Primary Test Matrix",
            "Effect size and p-value matrix across all primary predictor/outcome tests.",
        )
    for bundle in bundles:
        if f"_{_safe(bundle.plan.plan_id)}" in name:
            if name.startswith("robustness_bootstrap_"):
                return (
                    "robustness_bootstrap",
                    f"Bootstrap Sign Stability: {_display_label(bundle.plan.plan_id)}",
                    "Bootstrap sign stability for each primary test. Labels show predictor/outcome pairs rather than internal test ids.",
                )
            if name.startswith("negative_controls_"):
                return (
                    "negative_controls",
                    f"Negative Controls: {_display_label(bundle.plan.plan_id)}",
                    "Negative controls: green=passed negative control; red=failed negative control. Bars show effect estimates; p-values are not available in the current negative-control result schema.",
                )
            if name.startswith("missingness_"):
                return (
                    "missingness",
                    f"Variable Missingness: {_display_label(bundle.plan.plan_id)}",
                    "Missing rate for variables used by this experiment plan.",
                )
        for test in bundle.stats_result.tests if bundle.stats_result else []:
            if _safe(test.test_id) in name:
                pair = f"{test.predictor} -> {test.outcome}"
                short_pair = f"{_display_label(test.predictor)} -> {_display_label(test.outcome)}"
                if name.startswith("spearman_scatter_"):
                    return ("spearman_scatter", f"Spearman: {short_pair}", f"Full variable pair: {pair}.")
                if name.startswith("linear_regression_fit_"):
                    return ("linear_regression_fit", f"Linear Regression: {short_pair}", f"Full variable pair: {pair}.")
                if name.startswith("mixed_effects_fixed_effects_"):
                    return ("mixed_effects_fixed_effects", f"Mixed Effects: {short_pair}", f"Full variable pair: {pair}.")
    if name.startswith("ml_feature_importance_"):
        return ("ml_feature_importance", "ML Feature Importance", "Feature importance from the selected machine-learning model.")
    if name.startswith("ml_classification_confusion_"):
        return ("ml_classification_confusion", "ML Classification Confusion", "Observed versus predicted classification counts.")
    if name.startswith("ml_classification_roc_"):
        return ("ml_classification_roc", "ML Classification ROC", "ROC curves for classification models with available probabilities.")
    if name.startswith("ml_regression_predicted_observed_"):
        return ("ml_regression_predicted_observed", "ML Regression Predicted vs Observed", "Predicted versus observed regression outcomes.")
    return ("figure", path.stem, path.name)


def _write_html(path: Path, bundles: list[ExperimentResultBundle], figure_records: list[dict[str, str]], output_dir: Path) -> None:
    rows = []
    for bundle in bundles:
        tests = bundle.stats_result.tests if bundle.stats_result else []
        rows.append(
            "<tr>"
            f"<td>{escape(bundle.plan.plan_id)}</td>"
            f"<td>{escape(bundle.plan.hypothesis_title)}</td>"
            f"<td>{sum(1 for test in tests if test.passed)}/{len(tests)}</td>"
            f"<td>{escape(', '.join(sorted({test.method for test in tests})))}</td>"
            f"<td>{escape(bundle.ml_result.model_type if bundle.ml_result else '')}</td>"
            "</tr>"
        )
    image_tags = "\n".join(
        "<section>"
        f"<h2>{escape(record['title'])}</h2>"
        f"<p>{escape(record['caption'])}</p>"
        f'<img src="{escape(str(Path(record["path"]).relative_to(output_dir)))}" />'
        "</section>"
        for record in figure_records
        if Path(record["path"]).is_relative_to(output_dir)
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Experiment Visualizations</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; }}
    th {{ background: #f3f4f6; }}
    section {{ margin: 28px 0; }}
    img {{ max-width: 100%; border: 1px solid #e5e7eb; }}
    p {{ color: #4b5563; line-height: 1.45; }}
  </style>
</head>
<body>
  <h1>Experiment Visualizations</h1>
  <table>
    <thead><tr><th>Plan</th><th>Hypothesis</th><th>Tests Passed</th><th>Statistical Models</th><th>ML Models</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  {image_tags}
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def _stat_label(test: StatisticalTestResult) -> str:
    parts = [f"n={test.n}"]
    if test.effect is not None:
        parts.append(f"effect={test.effect:.3g}")
    if test.p_value is not None:
        parts.append(f"p={test.p_value:.3g}")
    return "\n".join(parts)


def _save(fig: plt.Figure, path: Path) -> Path:
    if not fig.get_constrained_layout():
        fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)[:120]


def _short(value: str, limit: int = 28) -> str:
    return value if len(value) <= limit else f"{value[: limit - 3]}..."


def _display_label(value: str, limit: int = 42) -> str:
    label = str(value)
    label = label.replace("experiment_plan_", "plan_")
    label = label.replace("timefreq_fALFF_0.01_0.08_over_0.01_0.25", "timefreq fALFF\n0.01-0.08 / 0.01-0.25")
    label = label.replace("global_signal_psd_power_", "global signal PSD ")
    label = label.replace("thalamus_frontoparietal_FC", "thalamus-frontoparietal FC")
    label = label.replace("thalamus_salience_FC", "thalamus-salience FC")
    label = label.replace("thalamus_DMN_FC", "thalamus-DMN FC")
    label = label.replace("frontoparietal_FC", "frontoparietal FC")
    label = label.replace("salience_FC", "salience FC")
    label = label.replace("DMN_FC", "DMN FC")
    label = label.replace("_", " ")
    return _short(label, limit)


def _wrap_label(value: str, width: int) -> str:
    lines = []
    for part in str(value).split("\n"):
        wrapped = textwrap.wrap(part, width=width, break_long_words=False, break_on_hyphens=False)
        lines.extend(wrapped or [part])
    return "\n".join(lines)


def _wrap_title(value: str) -> str:
    return _wrap_label(value, 58)


def _test_pair_label(bundle: ExperimentResultBundle, test_id: str) -> str:
    for test in bundle.stats_result.tests if bundle.stats_result else []:
        if test.test_id == test_id:
            return f"{_display_label(test.predictor)} -> {_display_label(test.outcome)}"
    return _display_label(test_id)
