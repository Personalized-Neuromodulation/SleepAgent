#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ITERATIONS="${1:-${DISCOVERY_ITERATIONS:-2}}"
BASE_LOOP_CONFIG="${2:-configs/discovery_loop_config.yaml}"

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p logs
LOG_FILE="logs/run_all_tests_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[run_all_tests] project_root=$PROJECT_ROOT"
echo "[run_all_tests] iterations=$ITERATIONS"
echo "[run_all_tests] base_loop_config=$BASE_LOOP_CONFIG"
echo "[run_all_tests] log_file=$LOG_FILE"

if [[ ! "$ITERATIONS" =~ ^[1-9][0-9]*$ ]]; then
  echo "[run_all_tests] iterations must be a positive integer: $ITERATIONS" >&2
  exit 1
fi

if [[ ! -f "$BASE_LOOP_CONFIG" ]]; then
  echo "[run_all_tests] missing discovery loop config: $BASE_LOOP_CONFIG" >&2
  exit 1
fi

echo "[run_all_tests] [1/2] foundation -> online grounding/RAG"
bash scripts/run_foundation_grounding_online.sh

FULL_LOOP_CONFIG="$(mktemp /tmp/sleepagent_full_discovery_loop_XXXXXX.yaml)"
python - <<'PY' "$BASE_LOOP_CONFIG" "$FULL_LOOP_CONFIG" "$ITERATIONS"
import sys
from pathlib import Path

import yaml

source = Path(sys.argv[1])
target = Path(sys.argv[2])
iterations = int(sys.argv[3])

payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
payload.setdefault("discovery_loop", {})["max_iterations"] = iterations
payload.setdefault("discovery_loop", {})["enable_foundation_grounding_refresh"] = True
# The generated YAML includes:
# foundation:
# grounding:
payload["foundation"] = {"config_path": "configs/foundation_config.yaml"}
payload["literature"] = {
    "enabled": True,
    "config_path": "configs/literature_library_config.yaml",
    "query_config_path": "configs/literature_queries.yaml",
    "library_version": "sleep_literature_library_v1",
}
payload["grounding"] = {
    "config_path": "configs/grounding_config.yaml",
    "corpus_version": "sleepagent_grounding_data_constrained_v1",
}
target.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
print(f"[run_all_tests] full_loop_config={target}", flush=True)
PY

echo "[run_all_tests] [2/2] hypothesis -> experiment -> foundation update -> grounding refresh loop"
bash scripts/run_discovery_loop.sh "$FULL_LOOP_CONFIG" "$ITERATIONS"

echo "[run_all_tests] done"
