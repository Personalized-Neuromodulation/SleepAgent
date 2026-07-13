#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from split_stage_utils import context_for, initialize_subject_dirs, load_layered_module


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run or reuse fMRIPrep outputs for the split fMRI pipeline.")
    p.add_argument("--subject", default=None)
    return p


def main() -> int:
    args = parser().parse_args()
    mod = load_layered_module()
    ctx = context_for(mod, args.subject)
    initialize_subject_dirs(mod, ctx)
    if not ctx.bids_root.exists():
        _, bold = mod.prepare_bids(ctx)
        if not bold:
            raise FileNotFoundError("BIDS dataset has no BOLD run.")
    status = mod.attempt_fmriprep(ctx)
    located = mod.locate_fmriprep_outputs(ctx)
    bold_runs = mod.locate_fmriprep_bold_runs(ctx)
    copied = mod.copy_selected_fmriprep_figures(ctx)
    mod.prune_unselected_fmriprep_session_dirs(ctx)
    mod.write_json(
        ctx.output_subject / "logs" / "stage_fmriprep_qc.json",
        {"status": status, "located": located, "bold_runs": bold_runs, "copied_figures": [str(p) for p in copied]},
    )
    print(f"FMRIPREP_STATUS returncode={status.get('returncode')} runs={len(bold_runs)}")
    return 0 if status.get("returncode") == 0 and bold_runs else 2


if __name__ == "__main__":
    raise SystemExit(main())
