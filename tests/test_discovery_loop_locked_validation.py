from __future__ import annotations

from pathlib import Path

import yaml

from sleep_ai_scientist.common.io import read_json
from sleep_ai_scientist.discovery_loop import discovery_runner


def test_iteration_locked_validation_copies_connectome_figures_to_iteration_visuals(tmp_path: Path, monkeypatch) -> None:
    master = tmp_path / "master.csv"
    spec = tmp_path / "spec.json"
    master.write_text("subject,thalamus_DMN_FC\nsub-YZHC001,0.1\n", encoding="utf-8")
    spec.write_text('{"source":"grounding","candidate_fc":["thalamus_DMN_FC"]}', encoding="utf-8")

    def fake_validation(master_table, hypothesis_spec, *, output_dir, make_plots):
        figures = Path(output_dir) / "figures"
        figures.mkdir(parents=True, exist_ok=True)
        figure = figures / "mean_difference_connectome.png"
        figure.write_bytes(b"png")
        html = figures / "mean_difference_connectome_3d.html"
        html.write_text("<html>thalamus DMN</html>", encoding="utf-8")
        stale = Path(output_dir).parent / "figures" / "classification_weight_connectome.png"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes(b"stale")
        return {
            "metadata": {"n_subjects": 1},
            "connection_visualizations": [
                {"kind": "mean_difference_connectome", "renderer": "nilearn_connectome", "path": str(figure)},
                {"kind": "mean_difference_connectome_3d", "renderer": "nilearn_connectome_3d", "path": str(html)},
            ],
        }

    monkeypatch.setattr(discovery_runner, "run_grounding_locked_validation", fake_validation)

    result = discovery_runner._run_iteration_locked_validation(
        {"enabled": True, "master_table": str(master), "hypothesis_spec": str(spec)},
        iteration_dir=tmp_path / "iteration_001",
        verbose=False,
    )

    copied = tmp_path / "iteration_001" / "experiment" / "visuals" / "figures" / "mean_difference_connectome.png"
    copied_html = tmp_path / "iteration_001" / "experiment" / "visuals" / "figures" / "mean_difference_connectome_3d.html"
    assert result["status"] == "run"
    assert result["copied_figures"] == [str(copied), str(copied_html)]
    assert copied.read_bytes() == b"png"
    assert "thalamus" in copied_html.read_text(encoding="utf-8")
    assert not (tmp_path / "iteration_001" / "experiment" / "visuals" / "figures" / "classification_weight_connectome.png").exists()


def test_iteration_locked_validation_skips_when_inputs_missing(tmp_path: Path) -> None:
    result = discovery_runner._run_iteration_locked_validation(
        {"enabled": True, "master_table": str(tmp_path / "missing.csv"), "hypothesis_spec": str(tmp_path / "missing.json")},
        iteration_dir=tmp_path / "iteration_001",
        verbose=False,
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "missing_inputs"


def test_discovery_loop_runs_locked_validation_each_iteration(tmp_path: Path, monkeypatch) -> None:
    loop_config = tmp_path / "discovery_loop.yaml"
    hypothesis_config = tmp_path / "hypothesis.yaml"
    experiment_config = tmp_path / "experiment.yaml"
    foundation_config = tmp_path / "foundation.yaml"
    grounding_config = tmp_path / "grounding.yaml"
    hypothesis_config.write_text("paths: {}\n", encoding="utf-8")
    experiment_config.write_text("paths: {}\n", encoding="utf-8")
    foundation_config.write_text("{}\n", encoding="utf-8")
    grounding_config.write_text("{}\n", encoding="utf-8")
    loop_config.write_text(
        yaml.safe_dump(
            {
                "discovery_loop": {
                    "max_iterations": 2,
                    "verbose": False,
                    "enable_foundation_grounding_refresh": False,
                    "stop_conditions": {
                        "no_active_hypotheses": False,
                        "no_experimental_feedback": False,
                        "reward_convergence": {"enabled": False},
                    },
                },
                "hypothesis": {"config_path": str(hypothesis_config)},
                "experiment": {"config_path": str(experiment_config)},
                "foundation": {"config_path": str(foundation_config)},
                "grounding": {"config_path": str(grounding_config)},
                "paths": {
                    "loop_output_dir": str(tmp_path / "loop"),
                    "iteration_state": str(tmp_path / "loop" / "loop_state.json"),
                    "iteration_report": str(tmp_path / "report.md"),
                },
                "grounding_locked_validation": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )

    def fake_hypothesis(config_path):
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        out = Path(config["paths"]["output_hypotheses_dir"])
        out.mkdir(parents=True, exist_ok=True)
        (out / "hypothesis_pool.json").write_text('{"hypotheses":[{"hypothesis_id":"h1","status":"active"}]}', encoding="utf-8")
        (out / "top_k_hypotheses.json").write_text("[]", encoding="utf-8")
        return {"hypotheses": 1}

    def fake_experiment(config_path):
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        paths = config["paths"]
        Path(paths["experiment_results"]).parent.mkdir(parents=True, exist_ok=True)
        Path(paths["experiment_results"]).write_text('{"results":[]}', encoding="utf-8")
        Path(paths["experimental_feedback"]).write_text("[]", encoding="utf-8")
        Path(paths["experiment_visualizations"]).mkdir(parents=True, exist_ok=True)
        return {"plans": 1, "results": paths["experiment_results"], "experimental_feedback": paths["experimental_feedback"]}

    calls: list[str] = []

    def fake_locked(validation_cfg, *, iteration_dir, verbose):
        calls.append(Path(iteration_dir).name)
        return {"status": "run", "copied_figures": [str(Path(iteration_dir) / "experiment" / "visuals" / "figures" / "mean_difference_connectome.png")]}

    monkeypatch.setattr(discovery_runner, "run_hypothesis_pipeline", fake_hypothesis)
    monkeypatch.setattr(discovery_runner, "run_experiment_pipeline", fake_experiment)
    monkeypatch.setattr(discovery_runner, "_run_iteration_locked_validation", fake_locked)

    result = discovery_runner.run_discovery_loop(loop_config)

    assert result["iterations"] == 2
    assert calls == ["iteration_001", "iteration_002"]
    first_summary = read_json(tmp_path / "loop" / "iteration_001" / "loop_summary.json")
    assert first_summary["grounding_locked_validation"]["status"] == "run"
