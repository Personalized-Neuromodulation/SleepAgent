from pathlib import Path

from sleep_ai_scientist.common.io import read_json, write_json, write_yaml
from sleep_ai_scientist.discovery_loop.discovery_runner import run_discovery_loop


def test_discovery_loop_runs_iterations_and_snapshots(monkeypatch, tmp_path):
    hypothesis_dir = tmp_path / "hypotheses"
    experiment_dir = tmp_path / "experiments"
    reports_dir = tmp_path / "reports"
    feature_root = tmp_path / "features"
    feedback_path = hypothesis_dir / "experimental_feedback.json"
    reward_memory = tmp_path / "reward_memory.json"
    hypothesis_report = reports_dir / "hypothesis_report.md"
    experiment_report = reports_dir / "experiment_report.md"
    experiment_results = experiment_dir / "experiment_results.json"

    hypothesis_config = tmp_path / "hypothesis_config.yaml"
    experiment_config = tmp_path / "experiment_config.yaml"
    loop_config = tmp_path / "discovery_loop_config.yaml"

    write_yaml(
        hypothesis_config,
        {
            "paths": {
                "output_hypotheses_dir": str(hypothesis_dir),
                "experimental_feedback": str(feedback_path),
                "reward_memory": str(reward_memory),
                "report_path": str(hypothesis_report),
            }
        },
    )
    write_yaml(
        experiment_config,
        {
            "feature_extraction": {"output_root": str(feature_root)},
            "paths": {
                "experiment_output_dir": str(experiment_dir),
                "experiment_results": str(experiment_results),
                "experimental_feedback": str(feedback_path),
                "experiment_report": str(experiment_report),
            },
        },
    )
    write_yaml(
        loop_config,
        {
            "discovery_loop": {
                "run_id": "test_loop",
                "max_iterations": 2,
                "verbose": False,
                "snapshot_features": True,
                "stop_conditions": {
                    "no_active_hypotheses": True,
                    "no_experimental_feedback": False,
                    "reward_convergence": {"enabled": False},
                },
            },
            "hypothesis": {"config_path": str(hypothesis_config)},
            "experiment": {"config_path": str(experiment_config)},
            "paths": {
                "loop_output_dir": str(tmp_path / "loop"),
                "iteration_state": str(tmp_path / "loop" / "loop_state.json"),
                "iteration_report": str(reports_dir / "discovery_loop_report.md"),
            },
        },
    )

    calls = {"hypothesis": 0, "experiment": 0}

    def fake_hypothesis_pipeline(config_path):
        calls["hypothesis"] += 1
        hypothesis_id = f"hyp-{calls['hypothesis']}"
        write_json(
            hypothesis_dir / "hypothesis_pool.json",
            [
                {
                    "hypothesis_id": hypothesis_id,
                    "title": f"Hypothesis {calls['hypothesis']}",
                    "status": "active",
                    "elo_rating": 1300 + calls["hypothesis"],
                }
            ],
        )
        write_json(hypothesis_dir / "top_k_hypotheses.json", [{"hypothesis_id": hypothesis_id, "status": "active"}])
        hypothesis_report.parent.mkdir(parents=True, exist_ok=True)
        hypothesis_report.write_text("hypothesis report", encoding="utf-8")
        return {"hypotheses": 1, "active": 1}

    def fake_experiment_pipeline(config_path):
        calls["experiment"] += 1
        write_json(experiment_results, [{"plan_id": f"plan-{calls['experiment']}"}])
        write_json(
            feedback_path,
            [
                {
                    "feedback_id": f"fb-{calls['experiment']}",
                    "hypothesis_id": f"hyp-{calls['experiment']}",
                    "computed_reward": 0.5,
                }
            ],
        )
        experiment_report.parent.mkdir(parents=True, exist_ok=True)
        experiment_report.write_text("experiment report", encoding="utf-8")
        (feature_root / "fmri" / f"plan-{calls['experiment']}").mkdir(parents=True, exist_ok=True)
        return {"plans": 1, "results": str(experiment_results)}

    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_hypothesis_pipeline", fake_hypothesis_pipeline)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_experiment_pipeline", fake_experiment_pipeline)

    summary = run_discovery_loop(loop_config)

    assert summary["iterations"] == 2
    assert summary["stop_reason"] == "max_iterations"
    assert calls == {"hypothesis": 2, "experiment": 2}
    assert (tmp_path / "loop" / "iteration_001" / "hypothesis" / "hypothesis_pool.json").exists()
    assert (tmp_path / "loop" / "iteration_002" / "experiment" / "experiment_results.json").exists()
    assert (tmp_path / "loop" / "iteration_002" / "features" / "fmri").exists()
    state = read_json(tmp_path / "loop" / "loop_state.json")
    assert len(state["iterations"]) == 2
    assert (reports_dir / "discovery_loop_report.md").exists()
