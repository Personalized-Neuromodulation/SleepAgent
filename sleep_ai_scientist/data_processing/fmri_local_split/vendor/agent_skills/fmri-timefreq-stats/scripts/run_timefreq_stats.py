#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from split_stage_utils import clean_bold_runs, context_for, initialize_subject_dirs, load_layered_module


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compute ALFF/fALFF time-frequency summaries and QC summary.")
    p.add_argument("--subject", default=None)
    return p


def main() -> int:
    args = parser().parse_args()
    mod = load_layered_module()
    ctx = context_for(mod, args.subject)
    initialize_subject_dirs(mod, ctx)
    runs = clean_bold_runs(mod, ctx)
    if not runs:
        raise FileNotFoundError("No clean BOLD data found; run fmri-denoise-regressors first.")
    metrics = {}
    for run in runs:
        clean_bold = Path(run["clean_bold"])
        img = mod.nib.load(str(clean_bold))
        zooms = img.header.get_zooms()
        tr = float(zooms[3]) if len(zooms) > 3 else 2.0
        metrics[run["base"]] = mod.time_frequency(ctx, clean_bold, tr=tr)
    payload = {"runs": metrics}
    mod.qc_statistics(ctx, {"attempted": False, "returncode": 0, "reason": "timefreq-only stage reused existing preprocessing outputs"}, payload)
    mod.write_json(ctx.output_subject / "logs" / "stage_timefreq_stats.json", payload)
    print(f"TIMEFREQ_READY runs={len(metrics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
