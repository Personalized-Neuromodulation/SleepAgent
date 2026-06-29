from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from neuro_research_agent.core.io import write_json


def progress_log(stage: str, agent: str, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{stage}] agent={agent} | {message}", flush=True)


def _find_conda_env_python(env_name: str) -> Path | None:
    explicit_python = os.environ.get("NEURO_RESEARCH_AGENT_PYTHON")
    if explicit_python and Path(explicit_python).exists():
        return Path(explicit_python)

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix and Path(conda_prefix).name == env_name:
        candidate = Path(conda_prefix) / "bin" / "python"
        if candidate.exists():
            return candidate

    try:
        completed = subprocess.run(
            ["conda", "env", "list", "--json"],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if completed.returncode == 0:
            payload = json.loads(completed.stdout)
            for env_path in payload.get("envs", []):
                env_root = Path(env_path)
                if env_root.name == env_name:
                    candidate = env_root / "bin" / "python"
                    if candidate.exists():
                        return candidate
    except Exception:
        pass

    for root in (
        Path.home() / "anaconda3" / "envs" / env_name,
        Path.home() / "miniconda3" / "envs" / env_name,
        Path.home() / ".conda" / "envs" / env_name,
        Path("/opt/conda/envs") / env_name,
    ):
        candidate = root / "bin" / "python"
        if candidate.exists():
            return candidate
    return None


def execute_python_script(
    script_path: Path,
    data_root: Path,
    output_dir: Path,
    subject: str | None,
    session: str | None,
    timeout: int = 240,
) -> tuple[int, str, str]:
    env_name = os.environ.get("NEURO_RESEARCH_AGENT_KERNEL", "agent")
    python_path = _find_conda_env_python(env_name)
    if python_path is None:
        import sys

        python_path = Path(sys.executable)
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(python_path),
        str(script_path),
        "--input-root",
        str(data_root),
        "--output-dir",
        str(output_dir),
    ]
    if subject:
        cmd.extend(["--subject", subject])
    if session:
        cmd.extend(["--session", session])
    completed = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def run_generated_experiments(
    generated_code: list[dict[str, Any]],
    output_root: Path,
    data_root: Path | None,
    subject: str | None,
    session: str | None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    execution_root = output_root / "execution"

    for idx, item in enumerate(generated_code, start=1):
        paradigm_id = item["paradigm"]
        experiment_id = item.get("experiment_id", "")
        innovation_id = item.get("innovation_id", "")
        experiment_dir = item.get("experiment_dir", "")
        script_path = Path(item.get("script") or item.get("path", ""))
        if item.get("execution_dir") or item.get("experiment_dir"):
            paradigm_out = Path(item.get("execution_dir") or item.get("experiment_dir"))
        else:
            execution_root.mkdir(parents=True, exist_ok=True)
            paradigm_out = execution_root / paradigm_id
        paradigm_out.mkdir(parents=True, exist_ok=True)
        execution_json_path = paradigm_out / f"{paradigm_id}_execution.json"
        if data_root is None:
            progress_log("experiment_execution", "analyst_agent.run_generated_experiments", f"({idx}/{len(generated_code)}) 跳过实验: analysis_route={paradigm_id}, reason=No neuroscience data root supplied")
            record = {
                "experiment_id": experiment_id,
                "innovation_id": innovation_id,
                "experiment_dir": experiment_dir,
                "paradigm": paradigm_id,
                "script": str(script_path) if script_path else "",
                "output_dir": str(paradigm_out),
                "returncode": 2,
                "status": "not_executed",
                "reason": "No neuroscience data root supplied.",
            }
            write_json(execution_json_path, record)
            results.append(record)
            continue
        if not script_path or not script_path.exists() or script_path.suffix != ".py":
            record = {
                "experiment_id": experiment_id,
                "innovation_id": innovation_id,
                "experiment_dir": experiment_dir,
                "paradigm": paradigm_id,
                "script": str(script_path) if script_path else "",
                "output_dir": str(paradigm_out),
                "returncode": 2,
                "status": "not_executed",
                "reason": "Experiment Python script is missing.",
            }
            write_json(execution_json_path, record)
            results.append(record)
            continue

        started = time.time()
        progress_log("experiment_execution", "analyst_agent.run_generated_experiments", f"({idx}/{len(generated_code)}) 开始执行 py 实验代码: innovation={innovation_id or 'NA'}, analysis_route={paradigm_id}, script={script_path}")
        try:
            returncode, stdout, stderr = execute_python_script(script_path, data_root, paradigm_out, subject, session)
        except Exception as exc:
            record = {
                "experiment_id": experiment_id,
                "innovation_id": innovation_id,
                "experiment_dir": experiment_dir,
                "paradigm": paradigm_id,
                "script": str(script_path),
                "output_dir": str(paradigm_out),
                "returncode": 1,
                "elapsed_seconds": int(time.time() - started),
                "stdout": "",
                "stderr": f"{type(exc).__name__}: {exc}",
                "result_json": "",
                "status": "failed",
            }
            write_json(execution_json_path, record)
            results.append(record)
            progress_log("experiment_execution", "analyst_agent.run_generated_experiments", f"({idx}/{len(generated_code)}) py 实验代码执行失败: innovation={innovation_id or 'NA'}, analysis_route={paradigm_id}, error={type(exc).__name__}: {exc}")
            continue
        result_path = paradigm_out / f"{paradigm_id}_result.json"
        if not result_path.exists():
            fallback_result_path = paradigm_out / "latest_result.json"
            result_path = fallback_result_path if fallback_result_path.exists() else result_path
        result_payload: dict[str, Any] = {}
        if result_path.exists():
            try:
                import json

                result_payload = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                result_payload = {}
        result_status = result_payload.get("status", "")
        record = {
            "experiment_id": experiment_id,
            "innovation_id": innovation_id,
            "experiment_dir": experiment_dir,
            "paradigm": paradigm_id,
            "script": str(script_path),
            "output_dir": str(paradigm_out),
            "returncode": returncode,
            "elapsed_seconds": int(time.time() - started),
            "stdout": stdout[-8000:],
            "stderr": stderr[-8000:],
            "result_json": str(result_path) if result_path.exists() else "",
            "result_status": result_status,
            "status": result_status or ("completed" if returncode == 0 else "failed"),
        }
        write_json(execution_json_path, record)
        results.append(record)
        progress_log(
            "experiment_execution",
            "analyst_agent.run_generated_experiments",
            f"({idx}/{len(generated_code)}) py 实验代码执行完成: innovation={innovation_id or 'NA'}, analysis_route={paradigm_id}, status={record['status']}, returncode={returncode}, elapsed_seconds={record['elapsed_seconds']}",
        )
    return results
