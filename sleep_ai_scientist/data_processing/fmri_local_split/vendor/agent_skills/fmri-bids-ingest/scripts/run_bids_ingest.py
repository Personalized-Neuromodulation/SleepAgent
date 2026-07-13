#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from split_stage_utils import context_for, initialize_subject_dirs, load_layered_module


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build the subject BIDS dataset for the split fMRI pipeline.")
    p.add_argument("--subject", default=None)
    return p


def main() -> int:
    args = parser().parse_args()
    mod = load_layered_module()
    ctx = context_for(mod, args.subject)
    initialize_subject_dirs(mod, ctx)
    anat, bold = mod.prepare_bids(ctx)
    mod.write_json(ctx.output_subject / "logs" / "stage_bids_ingest.json", {"anat": [str(p) for p in anat], "bold": [str(p) for p in bold]})
    print(f"BIDS_READY {ctx.bids_root}")
    return 0 if bold else 2


if __name__ == "__main__":
    raise SystemExit(main())
