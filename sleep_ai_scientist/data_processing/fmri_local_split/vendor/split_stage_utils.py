#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUN_LAYERED = ROOT / "run_layered_skill_analysis.py"


def load_layered_module():
    spec = importlib.util.spec_from_file_location("fmri_split_layered", RUN_LAYERED)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def context_for(module, subject: str | None = None):
    if subject:
        subject_id = module.bids_subject_id(subject)
        candidates = [
            module.INPUT_ROOT / subject,
            module.INPUT_ROOT / subject.removeprefix("sub-"),
            module.INPUT_ROOT / subject_id,
        ]
        input_subject = next((path for path in candidates if path.exists() and path.is_dir()), candidates[0])
    else:
        subject_id, input_subject = module.choose_subject()
    output_subject = module.DERIVATIVES_ROOT / subject_id
    return module.RunContext(
        subject=subject_id,
        input_subject=input_subject,
        output_subject=output_subject,
        bids_root=module.OUTPUT_ROOT,
        report={"subject": subject_id, "steps": {}},
    )


def initialize_subject_dirs(module, ctx) -> None:
    module.ensure_dirs(ctx)
    for session in sorted(module.selected_session_names(ctx.input_subject)):
        module.ensure_session_analysis_dirs(ctx, session)
    module.prune_legacy_top_level_dirs(ctx)


def clean_bold_runs(module, ctx) -> list[dict]:
    runs = []
    for session in sorted(module.selected_session_names(ctx.input_subject)):
        clean_dir = ctx.output_subject / session / "clean_data" / "volume"
        reg_dir = ctx.output_subject / session / "clean_data_regressor" / "volume"
        for clean_bold in sorted(clean_dir.glob("*_12rp_50pca_csf_wm.nii.gz")):
            stem = clean_bold.name.removesuffix(".nii.gz").removesuffix(".nii")
            base = stem.split("_12rp_", 1)[0] if "_12rp_" in stem else stem
            confounds = sorted(reg_dir.glob(f"{base}_run-*_desc-confounds_timeseries.tsv"))
            if not confounds:
                confounds = sorted(reg_dir.glob("*desc-confounds_timeseries.tsv"))
            runs.append({"session": session, "base": base, "clean_bold": clean_bold, "confounds": confounds[0] if confounds else None})
    return runs


def clean_surface_files(module, ctx) -> list[Path]:
    files: list[Path] = []
    for session in sorted(module.selected_session_names(ctx.input_subject)):
        files.extend(sorted((ctx.output_subject / session / "clean_data" / "surface").glob("*.gii")))
    return files
