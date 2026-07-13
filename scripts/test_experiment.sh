#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

CONFIG_PATH="${1:-configs/experiment_config.yaml}"

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[test_experiment] project_root=$PROJECT_ROOT"
echo "[test_experiment] config=$CONFIG_PATH"
echo "[test_experiment] python=$(command -v python)"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "[test_experiment] missing config: $CONFIG_PATH" >&2
  exit 1
fi

python - <<'PY' "$CONFIG_PATH"
import sys
from pathlib import Path

from sleep_ai_scientist.common.io import read_yaml

config_path = Path(sys.argv[1])
config = read_yaml(config_path)
paths = config.get("paths", {})

required = {
    "hypothesis_pool": paths.get("hypothesis_pool", "outputs/hypotheses/hypothesis_pool.json"),
    "data_profile": paths.get("data_profile", "outputs/profiles/analysis_ready_profile.yaml"),
}

missing = [f"{name}={path}" for name, path in required.items() if path and not Path(path).exists()]
if missing:
    raise SystemExit("[test_experiment] missing required input:\n  " + "\n  ".join(missing))

feature_config = config.get("feature_extraction", {})
if feature_config.get("enabled", False):
    print(f"[test_experiment] feature_extraction=enabled output_root={feature_config.get('output_root')}", flush=True)
    print(f"[test_experiment] modalities={feature_config.get('modalities', 'auto')}", flush=True)

data_processing = config.get("data_processing", {})
if data_processing.get("enabled", False):
    print(f"[test_experiment] data_processing=enabled backend={data_processing.get('backend')}", flush=True)
else:
    print("[test_experiment] data_processing=disabled", flush=True)
PY

python - <<'PY' "$CONFIG_PATH"
import json
import sys

from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline

summary = run_experiment_pipeline(sys.argv[1])
print("[test_experiment] summary=" + json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
PY

echo "[test_experiment] done"
