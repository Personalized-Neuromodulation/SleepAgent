#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

HYPOTHESIS_CONFIG="${1:-configs/hypothesis_config.yaml}"
EXPERIMENT_CONFIG="${2:-configs/experiment_config.yaml}"

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[joint_test] project_root=$PROJECT_ROOT"
echo "[joint_test] hypothesis_config=$HYPOTHESIS_CONFIG"
echo "[joint_test] experiment_config=$EXPERIMENT_CONFIG"
echo "[joint_test] python=$(command -v python)"

if [[ ! -f "$HYPOTHESIS_CONFIG" ]]; then
  echo "[joint_test] missing hypothesis config: $HYPOTHESIS_CONFIG" >&2
  exit 1
fi

if [[ ! -f "$EXPERIMENT_CONFIG" ]]; then
  echo "[joint_test] missing experiment config: $EXPERIMENT_CONFIG" >&2
  exit 1
fi

python - <<'PY' "$HYPOTHESIS_CONFIG" "$EXPERIMENT_CONFIG"
import sys
from pathlib import Path

from sleep_ai_scientist.common.io import read_yaml

hypothesis_config_path = Path(sys.argv[1])
experiment_config_path = Path(sys.argv[2])
hypothesis_config = read_yaml(hypothesis_config_path)
experiment_config = read_yaml(experiment_config_path)

hypothesis_paths = hypothesis_config.get("paths", {})
experiment_paths = experiment_config.get("paths", {})

required_hypothesis_inputs = {
    "evidence_table_json": hypothesis_paths.get("evidence_table_json", "outputs/grounding/evidence_table.json"),
}
missing = [
    f"{name}={path}"
    for name, path in required_hypothesis_inputs.items()
    if path and not Path(path).exists()
]
if missing:
    raise SystemExit("[joint_test] missing hypothesis input:\n  " + "\n  ".join(missing))

data_profile = experiment_paths.get("data_profile", "outputs/profiles/analysis_ready_profile.yaml")
if data_profile and not Path(data_profile).exists():
    raise SystemExit(f"[joint_test] missing experiment data_profile={data_profile}")

hypothesis_output_dir = Path(hypothesis_paths.get("output_hypotheses_dir", "outputs/hypotheses"))
hypothesis_pool = hypothesis_output_dir / "hypothesis_pool.json"
experiment_pool = Path(experiment_paths.get("hypothesis_pool", "outputs/hypotheses/hypothesis_pool.json"))

print(f"[joint_test] expected_hypothesis_pool={hypothesis_pool}", flush=True)
print(f"[joint_test] experiment_reads_hypothesis_pool={experiment_pool}", flush=True)
if hypothesis_pool != experiment_pool:
    print(
        "[joint_test] warning: experiment config reads a different hypothesis_pool path; "
        "make sure it points to the hypothesis output if this is intentional.",
        flush=True,
    )

llm_provider = hypothesis_config.get("llm_provider", "ollama")
print(f"[joint_test] hypothesis_llm_provider={llm_provider}", flush=True)
print(f"[joint_test] experiment_llm_enabled={experiment_config.get('experiment', {}).get('llm', {}).get('enabled')}", flush=True)
PY

echo "[joint_test] running hypothesis pipeline"
python - <<'PY' "$HYPOTHESIS_CONFIG"
import json
import sys

from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline

summary = run_hypothesis_pipeline(sys.argv[1])
print("[joint_test] hypothesis_summary=" + json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
PY

python - <<'PY' "$HYPOTHESIS_CONFIG" "$EXPERIMENT_CONFIG"
import sys
from pathlib import Path

from sleep_ai_scientist.common.io import read_yaml

hypothesis_config = read_yaml(Path(sys.argv[1]))
experiment_config = read_yaml(Path(sys.argv[2]))
hypothesis_pool = Path(hypothesis_config.get("paths", {}).get("output_hypotheses_dir", "outputs/hypotheses")) / "hypothesis_pool.json"
experiment_pool = Path(experiment_config.get("paths", {}).get("hypothesis_pool", "outputs/hypotheses/hypothesis_pool.json"))

missing = []
for name, path in {"hypothesis_pool": hypothesis_pool, "experiment_hypothesis_pool": experiment_pool}.items():
    if not path.exists() or path.stat().st_size == 0:
        missing.append(f"{name}={path}")
if missing:
    raise SystemExit("[joint_test] hypothesis output missing before experiment:\n  " + "\n  ".join(missing))
PY

echo "[joint_test] running experiment pipeline"
python - <<'PY' "$EXPERIMENT_CONFIG"
import json
import sys

from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline

summary = run_experiment_pipeline(sys.argv[1])
print("[joint_test] experiment_summary=" + json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
PY

echo "[joint_test] done"
