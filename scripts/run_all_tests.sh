#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ITERATIONS="${1:-}"
BASE_LOOP_CONFIG="${2:-configs/discovery_loop_config.yaml}"

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p logs
LOG_FILE="logs/run_all_tests_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[run_all_tests] project_root=$PROJECT_ROOT"
echo "[run_all_tests] iterations=${ITERATIONS:-config_default}"
echo "[run_all_tests] base_loop_config=$BASE_LOOP_CONFIG"
echo "[run_all_tests] log_file=$LOG_FILE"

if [[ -n "$ITERATIONS" && ! "$ITERATIONS" =~ ^[1-9][0-9]*$ ]]; then
  echo "[run_all_tests] iterations must be a positive integer: $ITERATIONS" >&2
  exit 1
fi

if [[ ! -f "$BASE_LOOP_CONFIG" ]]; then
  echo "[run_all_tests] missing discovery loop config: $BASE_LOOP_CONFIG" >&2
  exit 1
fi

echo "[run_all_tests] [1/4] foundation -> online grounding/RAG"
bash scripts/run_foundation_grounding_online.sh

SCALE_SOURCEDATA_ROOT="${SLEEPAGENT_SCALE_SOURCEDATA_ROOT:-/data/fmri_agent/multimodal_sleep_data/bids/sourcedata}"
FMRI_DERIVATIVES_ROOT="${SLEEPAGENT_FMRI_DERIVATIVES_ROOT:-/data/fmri_agent/multimodal_sleep_data/bids/derivatives/FMRIPREP}"
FOUNDATION_MASTER_TABLE="${SLEEPAGENT_FOUNDATION_MASTER_TABLE:-data/foundation/multimodal_master_table.csv}"
GROUNDING_HEALTH_SPEC="${SLEEPAGENT_GROUNDING_HEALTH_SPEC:-configs/grounding_health_fc_hypothesis.json}"
CLOSED_LOOP_SCALE_DIR="${SLEEPAGENT_CLOSED_LOOP_SCALE_DIR:-outputs/scale_features}"
CLOSED_LOOP_VALIDATION_DIR="${SLEEPAGENT_CLOSED_LOOP_VALIDATION_DIR:-outputs/group_contrast/grounding_candidate_fc}"
CLOSED_LOOP_MERGED_TABLE="$CLOSED_LOOP_SCALE_DIR/multimodal_master_table_with_scales.csv"

echo "[run_all_tests] [2/4] pre-experiment scale/fMRI feature extraction"
echo "[run_all_tests] closed_loop_scale_dir=$CLOSED_LOOP_SCALE_DIR"
python - "$SCALE_SOURCEDATA_ROOT" "$FMRI_DERIVATIVES_ROOT" "$FOUNDATION_MASTER_TABLE" "$CLOSED_LOOP_SCALE_DIR" <<'PY'
import sys
from pathlib import Path

import pandas as pd

from sleep_ai_scientist.feature_extraction.extractors.fmri_feature_extractor import FMRIFeatureExtractor
from sleep_ai_scientist.feature_extraction.extractors.multimodal_merger import MultimodalMerger
from sleep_ai_scientist.feature_extraction.extractors.scale_feature_extractor import ScaleFeatureExtractor
from sleep_ai_scientist.feature_extraction.schemas import FeatureTable

scale_root = Path(sys.argv[1])
fmri_derivatives_root = Path(sys.argv[2])
master_table = Path(sys.argv[3])
scale_dir = Path(sys.argv[4])

scale_table = ScaleFeatureExtractor({"input_root": str(scale_root)}).run(
    plan_id="run_all_tests_pre_experiment",
    output_dir=scale_dir,
)
if scale_table is None:
    raise SystemExit(f"[run_all_tests] no scale features extracted from {scale_root}")

fmri_table = FMRIFeatureExtractor({"derivatives_root": str(fmri_derivatives_root)}).run(
    plan_id="run_all_tests_pre_experiment",
    output_dir=scale_dir / "fmri",
)
if fmri_table is None:
    fmri_table = FeatureTable(modality="fmri", path=str(master_table))

merged_path = scale_dir / "multimodal_master_table_with_scales.csv"
MultimodalMerger().run(
    [
        fmri_table,
        scale_table,
    ],
    merged_path,
)

baseline = pd.read_csv(scale_table.path)
long_frame = pd.read_csv(scale_table.metadata["long_table"])
fmri = pd.read_csv(fmri_table.path)
merged = pd.read_csv(merged_path)
print(
    "[run_all_tests] pre_experiment_feature_summary "
    f"fmri_rows={len(fmri)} "
    f"baseline_rows={len(baseline)} "
    f"long_rows={len(long_frame)} "
    f"merged_rows={len(merged)} "
    f"merged_table={merged_path}",
    flush=True,
)
PY

FULL_LOOP_CONFIG="$(mktemp /tmp/sleepagent_full_discovery_loop_XXXXXX.yaml)"
python - <<'PY' "$BASE_LOOP_CONFIG" "$FULL_LOOP_CONFIG" "$ITERATIONS"
import sys
from pathlib import Path

import yaml

source = Path(sys.argv[1])
target = Path(sys.argv[2])
iterations = int(sys.argv[3]) if sys.argv[3] else None

payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
if iterations is not None:
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

echo "[run_all_tests] [3/4] hypothesis -> experiment -> foundation update -> grounding refresh loop"
bash scripts/run_discovery_loop.sh "$FULL_LOOP_CONFIG" "$ITERATIONS"

echo "[run_all_tests] [4/4] grounding candidate FC group contrast"
echo "[run_all_tests] closed_loop_validation_table=$CLOSED_LOOP_MERGED_TABLE"
echo "[run_all_tests] closed_loop_validation_dir=$CLOSED_LOOP_VALIDATION_DIR"
python - "$CLOSED_LOOP_MERGED_TABLE" "$GROUNDING_HEALTH_SPEC" "$CLOSED_LOOP_VALIDATION_DIR" <<'PY'
import sys
from pathlib import Path

import pandas as pd

from sleep_ai_scientist.experiment.grounding_validation import run_grounding_locked_validation

merged_path = Path(sys.argv[1])
hypothesis_spec = Path(sys.argv[2])
validation_dir = Path(sys.argv[3])

result = run_grounding_locked_validation(
    merged_path,
    hypothesis_spec,
    output_dir=validation_dir,
    make_plots=True,
)

merged = pd.read_csv(merged_path)
print(
    "[run_all_tests] group_contrast_summary "
    f"merged_rows={len(merged)} "
    f"validation_subjects={result['metadata']['n_subjects']} "
    f"validation_samples={result['metadata'].get('n_samples', result['metadata']['n_subjects'])} "
    f"healthy_samples={result['metadata']['n_healthy']} "
    f"nonhealthy_samples={result['metadata']['n_nonhealthy']} "
    f"task={result['statistical_model']['task']} "
    f"feature_stats={result['feature_stats']} "
    f"group_symptom_stats={result['group_symptom_stats']}",
    flush=True,
)
PY

echo "[run_all_tests] done"
