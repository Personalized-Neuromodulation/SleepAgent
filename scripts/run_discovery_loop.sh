#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

CONFIG_PATH="${1:-configs/discovery_loop_config.yaml}"
ITERATIONS="${2:-}"

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p logs
LOG_FILE="logs/run_discovery_loop_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[run_discovery_loop] project_root=$PROJECT_ROOT"
echo "[run_discovery_loop] config=$CONFIG_PATH"
echo "[run_discovery_loop] iterations=${ITERATIONS:-config_default}"
echo "[run_discovery_loop] python=$(command -v python)"
echo "[run_discovery_loop] log_file=$LOG_FILE"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "[run_discovery_loop] missing config: $CONFIG_PATH" >&2
  exit 1
fi

if [[ -n "$ITERATIONS" && ! "$ITERATIONS" =~ ^[1-9][0-9]*$ ]]; then
  echo "[run_discovery_loop] iterations must be a positive integer: $ITERATIONS" >&2
  exit 1
fi

RUN_CONFIG_PATH="$CONFIG_PATH"
if [[ -n "$ITERATIONS" ]]; then
  RUN_CONFIG_PATH="$(mktemp /tmp/sleepagent_discovery_loop_XXXXXX.yaml)"
  python - "$CONFIG_PATH" "$RUN_CONFIG_PATH" "$ITERATIONS" <<'PY'
import sys
from pathlib import Path

import yaml

source = Path(sys.argv[1])
target = Path(sys.argv[2])
iterations = int(sys.argv[3])

payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
payload.setdefault("discovery_loop", {})["max_iterations"] = iterations
target.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
print(f"[run_discovery_loop] generated_config={target}", flush=True)
PY
fi

python - "$RUN_CONFIG_PATH" <<'PY'
import sys
from pathlib import Path

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml

loop_config_path = Path(sys.argv[1])
loop_config = read_yaml(loop_config_path)
hypothesis_config_path = resolve_path(loop_config.get("hypothesis", {}).get("config_path", "configs/hypothesis_config.yaml"))
experiment_config_path = resolve_path(loop_config.get("experiment", {}).get("config_path", "configs/experiment_config.yaml"))

print(f"[run_discovery_loop] effective_config={loop_config_path}", flush=True)
print(f"[run_discovery_loop] max_iterations={loop_config.get('discovery_loop', {}).get('max_iterations')}", flush=True)
print(f"[run_discovery_loop] hypothesis_config={hypothesis_config_path}", flush=True)
print(f"[run_discovery_loop] experiment_config={experiment_config_path}", flush=True)

if not hypothesis_config_path.exists():
    raise SystemExit(f"[run_discovery_loop] missing hypothesis config: {hypothesis_config_path}")
if not experiment_config_path.exists():
    raise SystemExit(f"[run_discovery_loop] missing experiment config: {experiment_config_path}")

hypothesis_config = read_yaml(hypothesis_config_path)
experiment_config = read_yaml(experiment_config_path)
hypothesis_paths = hypothesis_config.get("paths", {})
experiment_paths = experiment_config.get("paths", {})

hypothesis_inputs = {
    "evidence_table_json": hypothesis_paths.get("evidence_table_json", "outputs/grounding/evidence_table.json"),
    "knowledge_graph_json": hypothesis_paths.get("knowledge_graph_json", "outputs/grounding/mechanism_graph.json"),
    "llm_evidence_context_json": hypothesis_paths.get("llm_evidence_context_json", "outputs/grounding/llm_evidence_context.json"),
    "llm_mechanism_context_json": hypothesis_paths.get("llm_mechanism_context_json", "outputs/grounding/llm_mechanism_context.json"),
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
        print(f"[run_discovery_loop] {prefix}.{name}=<unset> exists=false size=0", flush=True)
        return
    path = resolve_path(raw_path)
    exists = path.exists()
    size = path.stat().st_size if exists and path.is_file() else 0
    print(f"[run_discovery_loop] {prefix}.{name}={path} exists={str(exists).lower()} size={size}", flush=True)


print("[run_discovery_loop] hypothesis inputs:", flush=True)
for name, path in hypothesis_inputs.items():
    describe_path("hypothesis_input", name, path)

print("[run_discovery_loop] experiment inputs:", flush=True)
for name, path in experiment_inputs.items():
    describe_path("experiment_input", name, path)

required = {
    "hypothesis_input.evidence_table_json": hypothesis_inputs["evidence_table_json"],
    "hypothesis_input.knowledge_graph_json": hypothesis_inputs["knowledge_graph_json"],
    "experiment_input.data_profile": experiment_inputs["data_profile"],
}
missing = [f"{name}={resolve_path(path)}" for name, path in required.items() if path and not resolve_path(path).exists()]
if missing:
    raise SystemExit("[run_discovery_loop] missing required input:\n  " + "\n  ".join(missing))

hypothesis_output_dir = resolve_path(hypothesis_paths.get("output_hypotheses_dir", "outputs/hypotheses"))
expected_hypothesis_pool = hypothesis_output_dir / "hypothesis_pool.json"
experiment_pool = resolve_path(experiment_inputs["hypothesis_pool"])
print(f"[run_discovery_loop] expected_hypothesis_pool={expected_hypothesis_pool}", flush=True)
print(f"[run_discovery_loop] experiment_reads_hypothesis_pool={experiment_pool}", flush=True)
if expected_hypothesis_pool != experiment_pool:
    print("[run_discovery_loop] warning: experiment config reads a different hypothesis_pool path.", flush=True)
PY

python - "$RUN_CONFIG_PATH" <<'PY'
import sys

from sleep_ai_scientist.discovery_loop import run_discovery_loop

summary = run_discovery_loop(sys.argv[1])
print(
    "[run_discovery_loop] summary "
    f"run_id={summary.get('run_id')} "
    f"iterations={summary.get('iterations')} "
    f"stop_reason={summary.get('stop_reason')} "
    f"foundation_changed={summary.get('foundation_changed')} "
    f"grounding_refreshes={summary.get('grounding_refreshes')} "
    f"last_feedback={summary.get('last_experiment_feedback')} "
    f"loop_output_dir={summary.get('loop_output_dir')} "
    f"iteration_report={summary.get('iteration_report')}",
    flush=True,
)
PY
