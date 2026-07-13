#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "agent_skills" / "fmri-local-agent" / "scripts" / "fmri_local_agent.py"
LOCAL_AGENT_PYTHON = Path("/opt/anaconda3/envs/agent/bin/python")
DEFAULT_PYTHON = Path(os.environ.get("FMRI_AGENT_PYTHON", str(LOCAL_AGENT_PYTHON if LOCAL_AGENT_PYTHON.exists() else "python")))


def main() -> int:
    python = DEFAULT_PYTHON if DEFAULT_PYTHON.exists() else Path(sys.executable)
    cmd = [str(python), str(ENTRY), *sys.argv[1:]]
    return subprocess.call(cmd, env=os.environ.copy())


if __name__ == "__main__":
    raise SystemExit(main())
