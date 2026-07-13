#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

CONFIG_PATH="${1:-configs/discovery_loop_config.yaml}"

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[run_discovery_loop] project_root=$PROJECT_ROOT"
echo "[run_discovery_loop] config=$CONFIG_PATH"
echo "[run_discovery_loop] python=$(command -v python)"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "[run_discovery_loop] missing config: $CONFIG_PATH" >&2
  exit 1
fi

python - <<'PY' "$CONFIG_PATH"
import json
import sys

from sleep_ai_scientist.discovery_loop import run_discovery_loop

summary = run_discovery_loop(sys.argv[1])
print("[run_discovery_loop] summary=" + json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
PY
