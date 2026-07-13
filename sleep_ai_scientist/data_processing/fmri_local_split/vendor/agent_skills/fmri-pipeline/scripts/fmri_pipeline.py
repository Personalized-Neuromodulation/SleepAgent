#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LOCAL_AGENT_PYTHON = Path("/opt/anaconda3/envs/agent/bin/python")
DEFAULT_PYTHON = Path(os.environ.get("FMRI_AGENT_PYTHON", str(LOCAL_AGENT_PYTHON if LOCAL_AGENT_PYTHON.exists() else "python")))
START_TIME = time.monotonic()

STAGE_SCRIPTS = {
    "bids": ROOT / "agent_skills" / "fmri-bids-ingest" / "scripts" / "run_bids_ingest.py",
    "fmriprep": ROOT / "agent_skills" / "fmri-fmriprep-qc" / "scripts" / "run_fmriprep_qc.py",
    "denoise": ROOT / "agent_skills" / "fmri-denoise-regressors" / "scripts" / "run_denoise_regressors.py",
    "segment": ROOT / "agent_skills" / "fmri-surface-segment" / "scripts" / "run_surface_segment.py",
    "timefreq": ROOT / "agent_skills" / "fmri-timefreq-stats" / "scripts" / "run_timefreq_stats.py",
}
FULL_ORDER = ["bids", "fmriprep", "denoise", "segment", "timefreq"]
ALIASES = {
    "analyze": "full",
    "full": "full",
    "complete": "full",
    "bids-ingest": "bids",
    "fmriprep-qc": "fmriprep",
    "denoise-regressors": "denoise",
    "surface-segment": "segment",
    "timefreq-stats": "timefreq",
}


def elapsed() -> str:
    seconds = int(time.monotonic() - START_TIME)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def log_step(message: str) -> None:
    print(f"[{elapsed()}] {message}", flush=True)


def run_stage(stage: str, python: Path, passthrough: list[str]) -> int:
    script = STAGE_SCRIPTS[stage]
    executable = python if python.exists() else Path(sys.executable)
    cmd = [str(executable), str(script), *passthrough]
    log_step(f"pipeline: stage={stage} command={' '.join(cmd)}")
    started = time.monotonic()
    returncode = subprocess.call(cmd, env=os.environ.copy())
    log_step(f"pipeline: stage={stage} 完成 returncode={returncode}, elapsed_seconds={int(time.monotonic() - started)}")
    return int(returncode)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Split fMRI pipeline dispatcher. Each command runs executable skills.")
    p.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    sub = p.add_subparsers(dest="command", required=True)
    for command in ["full", "analyze", "bids", "fmriprep", "denoise", "segment", "timefreq"]:
        sp = sub.add_parser(command)
        sp.add_argument("args", nargs=argparse.REMAINDER)
    return p


def normalize(args: list[str]) -> list[str]:
    return args[1:] if args and args[0] == "--" else args


def main() -> int:
    ns = parser().parse_args()
    command = ALIASES.get(ns.command, ns.command)
    passthrough = normalize(ns.args)
    stages = FULL_ORDER if command == "full" else [command]
    for stage in stages:
        rc = run_stage(stage, ns.python, passthrough)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
