#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from split_stage_utils import context_for, initialize_subject_dirs, load_layered_module


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build nuisance regressors and clean BOLD/surface data.")
    p.add_argument("--subject", default=None)
    return p


def main() -> int:
    args = parser().parse_args()
    mod = load_layered_module()
    ctx = context_for(mod, args.subject)
    initialize_subject_dirs(mod, ctx)
    bold_runs = mod.locate_fmriprep_bold_runs(ctx)
    if not bold_runs:
        raise FileNotFoundError("No fMRIPrep BOLD/confounds runs found; run fmri-fmriprep-qc first.")
    processed = []
    for run in bold_runs:
        preproc_bold = Path(run["preproc_bold"])
        confounds_tsv = Path(run["confounds"])
        base = mod.standard_bold_base(preproc_bold)
        session = mod.session_from_bold_base(base)
        conf_path, reg_path, regressors, tr = mod.build_regressors_from_fmriprep(ctx, confounds_tsv, preproc_bold)
        _, preproc_data = mod.load_bold(preproc_bold)
        mask = np.nanmean(preproc_data.reshape(-1, preproc_data.shape[-1]), axis=1) != 0
        clean_path = ctx.output_subject / session / "clean_data" / "volume" / f"{base}_12rp_50pca_csf_wm.nii.gz"
        clean = mod.denoise_bold(ctx, preproc_bold, regressors, mask, clean_path)
        stat_csv, bad_json = mod.compute_outliers(ctx, clean, confounds_tsv, base)
        carpet = mod.plot_clean_carpet(ctx, clean, base, tr, confounds_tsv)
        surface_files = [Path(p) for p in run.get("surface_bold", [])]
        surface_clean = mod.denoise_surfaces(ctx, surface_files, regressors)
        fallback_surface = []
        if not surface_files:
            fallback_clean, fallback_surface = mod.project_clean_bold_to_fsnative_surfaces(ctx, clean, base)
            surface_clean.extend(fallback_clean)
        processed.append(
            {
                "base": base,
                "session": session,
                "confounds": str(conf_path),
                "regressors": str(reg_path),
                "clean_bold": str(clean),
                "outlier_stat": str(stat_csv),
                "bad_epoch_info": str(bad_json),
                "clean_carpetplot": str(carpet) if carpet else "",
                "clean_surface": [str(p) for p in surface_clean],
                "fallback_surface_transform": [str(p) for p in fallback_surface],
                "tr": tr,
            }
        )
    mod.write_json(ctx.output_subject / "logs" / "stage_denoise_regressors.json", {"processed_runs": processed})
    print(f"DENOISE_READY runs={len(processed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
