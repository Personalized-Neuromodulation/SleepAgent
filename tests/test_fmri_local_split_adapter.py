from pathlib import Path

from sleep_ai_scientist.data_processing.fmri_local_split.adapter import FMRILocalSplitConfig, _build_command, run_fmri_local_split


def test_fmri_local_split_adapter_builds_noninteractive_command(tmp_path):
    cfg = FMRILocalSplitConfig(
        input_root=str(tmp_path / "input"),
        output_root=str(tmp_path / "output"),
        subjects=["sub-ISM035"],
        surface_mode="0",
        mni_template="both",
        python="python",
        fs_license="/tmp/license.txt",
        subject_jobs=1,
    )

    command = _build_command(cfg, Path(cfg.input_root), Path(cfg.output_root))

    assert "analyze" in command
    assert "--input-root" in command
    assert "--output-root" in command
    assert "--surface-mode" in command
    assert "--mni-template" in command
    assert "--yes" in command
    assert "run" not in command


def test_fmri_local_split_skips_subject_with_complete_qc(tmp_path):
    sourcedata = tmp_path / "bids" / "sourcedata"
    qc_dir = tmp_path / "bids" / "derivatives" / "FMRIPREP" / "sub-001" / "ses-mri0" / "qc_statistics"
    (sourcedata / "sub-001" / "ses-mri0").mkdir(parents=True)
    qc_dir.mkdir(parents=True)
    for name in [
        "sub-001_ses-mri0_task-sleep0_desc-carpetplotSignalComparison.csv",
        "sub-001_ses-mri0_task-sleep0_desc-carpetplot_timeseries.csv",
        "sub-001_ses-mri0_task-sleep0_desc-carpetplot_bold.svg",
    ]:
        (qc_dir / name).write_text("ok\n", encoding="utf-8")

    result = run_fmri_local_split(
        {
            "input_root": str(sourcedata),
            "derivatives_root": str(tmp_path / "bids" / "derivatives" / "FMRIPREP"),
            "python": "python",
        }
    )

    assert result.returncode == 0
    assert result.skipped_subjects == ["sub-001"]
    assert result.processed_subjects == []
    assert result.commands == []
