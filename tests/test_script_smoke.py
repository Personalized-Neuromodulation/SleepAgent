from __future__ import annotations

import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_run_foundation_grounding_online_script_smoke(tmp_path):
    fake_bin = _fake_python_bin(tmp_path)
    env = _smoke_env(fake_bin)
    env["NCBI_EMAIL"] = "smoke@example.org"

    result = subprocess.run(
        ["bash", "scripts/run_foundation_grounding_online.sh"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    assert "API environment preflight" in result.stdout
    assert "[1/6] Build foundation" in result.stdout
    assert "[6/6] Foundation/grounding online flow validation complete" in result.stdout
    calls = (fake_bin / "python_calls.log").read_text(encoding="utf-8")
    assert "-m sleep_ai_scientist.cli foundation build" in calls
    assert "-m sleep_ai_scientist.cli literature build" in calls
    assert "-m pytest" not in calls


def test_run_discovery_loop_script_smoke(tmp_path):
    fake_bin = _fake_python_bin(tmp_path)
    env = _smoke_env(fake_bin)
    config = tmp_path / "discovery_loop_config.yaml"
    config.write_text(
        "discovery_loop:\n"
        "  max_iterations: 1\n"
        "hypothesis:\n"
        "  config_path: configs/hypothesis_config.yaml\n"
        "experiment:\n"
        "  config_path: configs/experiment_config.yaml\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", "scripts/run_discovery_loop.sh", str(config), "1"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    assert "[run_discovery_loop] project_root=" in result.stdout
    assert "[run_discovery_loop] config=" in result.stdout
    assert "[run_discovery_loop] iterations=1" in result.stdout
    calls = (fake_bin / "python_calls.log").read_text(encoding="utf-8")
    assert str(config) in calls
    assert any("- /tmp/sleepagent_discovery_loop_" in line for line in calls.splitlines())


def test_run_all_tests_script_runs_closed_loop_step(tmp_path):
    fake_bin = _fake_python_bin(tmp_path)
    env = _smoke_env(fake_bin)
    env["NCBI_EMAIL"] = "smoke@example.org"
    config = tmp_path / "discovery_loop_config.yaml"
    config.write_text("discovery_loop:\n  max_iterations: 1\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", "scripts/run_all_tests.sh", "", str(config)],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    pre_feature = "[run_all_tests] [2/4] pre-experiment scale/fMRI feature extraction"
    discovery = "[run_all_tests] [3/4] hypothesis -> experiment -> foundation update -> grounding refresh loop"
    validation = "[run_all_tests] [4/4] grounding candidate FC group contrast"
    assert pre_feature in result.stdout
    assert discovery in result.stdout
    assert validation in result.stdout
    assert result.stdout.index(pre_feature) < result.stdout.index(discovery) < result.stdout.index(validation)
    assert "[run_all_tests] closed_loop_scale_dir=outputs/scale_features" in result.stdout
    assert "[run_all_tests] closed_loop_validation_dir=outputs/group_contrast/grounding_candidate_fc" in result.stdout
    assert "[run_all_tests] closed_loop_validation_table=outputs/scale_features/multimodal_master_table_with_scales.csv" in result.stdout
    calls = (fake_bin / "python_calls.log").read_text(encoding="utf-8")
    assert "outputs/scale_features" in calls
    assert "configs/grounding_health_fc_hypothesis.json" in calls


def _smoke_env(fake_bin: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return env


def _fake_python_bin(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$(dirname \"$0\")/python_calls.log\"\n"
        "cat >/dev/null || true\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    return fake_bin
