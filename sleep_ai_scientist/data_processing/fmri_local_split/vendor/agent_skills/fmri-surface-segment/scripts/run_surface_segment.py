#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from split_stage_utils import clean_bold_runs, clean_surface_files, context_for, initialize_subject_dirs, load_layered_module


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Organize surface transforms and segment clean fMRI data by sleep labels.")
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
    for session in sorted({run["session"] for run in runs}):
        mod.reset_segment_outputs(ctx, session)
    segments = []
    for run in runs:
        segments.extend(mod.segment_bold(ctx, Path(run["clean_bold"]), tr=2.0))
    fmriprep_surface = []
    for run in mod.locate_fmriprep_bold_runs(ctx):
        fmriprep_surface.extend(Path(p) for p in run.get("surface_bold", []))
    if not fmriprep_surface:
        fmriprep_surface = mod.fallback_surface_transform_sources(ctx)
    surface_transform = mod.organize_surface_transform(ctx, fmriprep_surface)
    surface_segments = mod.segment_surfaces(ctx, clean_surface_files(mod, ctx), tr=2.0)
    mod.write_json(
        ctx.output_subject / "logs" / "stage_surface_segment.json",
        {
            "volume_segments": [str(p) for p in segments],
            "surface_transform": [str(p) for p in surface_transform],
            "surface_segments": [str(p) for p in surface_segments],
        },
    )
    print(f"SEGMENT_READY volume_files={len(segments)} surface_files={len(surface_segments)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
