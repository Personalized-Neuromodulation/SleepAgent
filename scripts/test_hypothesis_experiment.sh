#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

HYPOTHESIS_CONFIG="${1:-configs/hypothesis_config.yaml}"
EXPERIMENT_CONFIG="${2:-configs/experiment_config.yaml}"

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p logs
LOG_FILE="logs/test_hypothesis_experiment_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[joint_test] project_root=$PROJECT_ROOT"
echo "[joint_test] hypothesis_config=$HYPOTHESIS_CONFIG"
echo "[joint_test] experiment_config=$EXPERIMENT_CONFIG"
echo "[joint_test] python=$(command -v python)"
echo "[joint_test] log_file=$LOG_FILE"

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
    "knowledge_graph_json": hypothesis_paths.get("knowledge_graph_json", "outputs/grounding/mechanism_graph.json"),
}
optional_hypothesis_inputs = {
    "prior_hypotheses_json": hypothesis_paths.get("prior_hypotheses_json", "outputs/hypotheses/top_k_hypotheses.json"),
    "experimental_feedback": hypothesis_paths.get("experimental_feedback", "outputs/hypotheses/experimental_feedback.json"),
    "reward_memory": hypothesis_paths.get("reward_memory", "outputs/memory/reward_memory.json"),
    "context_blocks_json": hypothesis_paths.get("context_blocks_json", "outputs/hypotheses/context_blocks.json"),
}
experiment_inputs = {
    "hypothesis_pool": experiment_paths.get("hypothesis_pool", "outputs/hypotheses/hypothesis_pool.json"),
    "data_profile": experiment_paths.get("data_profile", "outputs/profiles/analysis_ready_profile.yaml"),
    "approved_variables": experiment_paths.get("approved_variables", "outputs/grounding/approved_variables_from_grounding.yaml"),
    "variable_mapping": experiment_paths.get("variable_mapping", "outputs/grounding/evidence_to_variable_map.yaml"),
}


def describe_path(prefix: str, name: str, raw_path: str | Path | None) -> None:
    if not raw_path:
        print(f"[joint_test] {prefix}.{name}=<unset> exists=false size=0", flush=True)
        return
    path = Path(raw_path)
    exists = path.exists()
    size = path.stat().st_size if exists and path.is_file() else 0
    print(f"[joint_test] {prefix}.{name}={path} exists={str(exists).lower()} size={size}", flush=True)


print("[joint_test] hypothesis inputs:", flush=True)
for name, path in {**required_hypothesis_inputs, **optional_hypothesis_inputs}.items():
    describe_path("hypothesis_input", name, path)

print("[joint_test] experiment inputs:", flush=True)
for name, path in experiment_inputs.items():
    describe_path("experiment_input", name, path)

missing = [
    f"{name}={path}"
    for name, path in required_hypothesis_inputs.items()
    if path and not Path(path).exists()
]
if missing:
    raise SystemExit("[joint_test] missing hypothesis input:\n  " + "\n  ".join(missing))

data_profile = experiment_inputs["data_profile"]
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
