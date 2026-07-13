from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


VENDOR_ROOT = Path(__file__).resolve().parent / "vendor"
VENDOR_ENTRY = VENDOR_ROOT / "agent_skills" / "fmri-local-agent" / "scripts" / "fmri_local_agent.py"


class FMRILocalSplitConfig(BaseModel):
    input_root: str
    output_root: str = ""
    derivatives_root: str = ""
    subjects: list[str] = Field(default_factory=list)
    surface_mode: str = "0"
    mni_template: str = "both"
    python: str = sys.executable
    fs_license: str = ""
    subject_jobs: int | None = None
    env: dict[str, str] = Field(default_factory=dict)


class FMRILocalSplitResult(BaseModel):
    returncode: int
    commands: list[list[str]] = Field(default_factory=list)
    output_root: str
    derivatives_root: str
    processed_subjects: list[str] = Field(default_factory=list)
    skipped_subjects: list[str] = Field(default_factory=list)
    incomplete_subjects: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)


def run_fmri_local_split(config: FMRILocalSplitConfig | dict[str, Any]) -> FMRILocalSplitResult:
    cfg = config if isinstance(config, FMRILocalSplitConfig) else FMRILocalSplitConfig(**config)
    input_root = Path(cfg.input_root).expanduser().resolve()
    derivatives_root = _resolve_derivatives_root(cfg, input_root)
    output_root = _resolve_output_root(cfg, input_root, derivatives_root)
    if not input_root.exists() or not input_root.is_dir():
        raise FileNotFoundError(f"fMRI input_root does not exist or is not a directory: {input_root}")
    if cfg.surface_mode not in {"0", "1"}:
        raise ValueError("surface_mode must be '0' or '1'")
    if cfg.mni_template not in {"both", "6", "2009"}:
        raise ValueError("mni_template must be 'both', '6', or '2009'")

    subject_inputs = _resolve_subject_inputs(input_root, cfg.subjects)
    commands: list[list[str]] = []
    logs: list[str] = []
    processed: list[str] = []
    skipped: list[str] = []
    incomplete: list[str] = []
    returncode = 0
    for subject_input in subject_inputs:
        subject_id = _bids_subject_id(subject_input.name)
        if _subject_qc_complete(subject_id, subject_input, derivatives_root):
            skipped.append(subject_id)
            continue
        incomplete.append(subject_id)
        cmd = _build_command(cfg, subject_input, output_root)
        commands.append(cmd)
        env = _build_env(cfg, input_root, output_root)
        proc = subprocess.run(cmd, cwd=str(VENDOR_ROOT), env=env, text=True, capture_output=True)
        log_path = output_root / "agent_log" / f"sleepagent_fmri_local_split_{subject_input.name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "COMMAND:\n"
            + " ".join(cmd)
            + "\n\nSTDOUT:\n"
            + proc.stdout
            + "\n\nSTDERR:\n"
            + proc.stderr
            + f"\n\nRETURN_CODE: {proc.returncode}\n",
            encoding="utf-8",
        )
        logs.append(str(log_path))
        if proc.returncode != 0:
            returncode = proc.returncode
            break
        processed.append(subject_id)

    return FMRILocalSplitResult(
        returncode=returncode,
        commands=commands,
        output_root=str(output_root),
        derivatives_root=str(derivatives_root),
        processed_subjects=processed,
        skipped_subjects=skipped,
        incomplete_subjects=incomplete,
        logs=logs,
    )


def _build_command(cfg: FMRILocalSplitConfig, input_root: Path, output_root: Path) -> list[str]:
    cmd = [
        cfg.python,
        str(VENDOR_ENTRY),
        "analyze",
        "--input-root",
        str(input_root),
        "--output-root",
        str(output_root),
        "--surface-mode",
        cfg.surface_mode,
        "--mni-template",
        cfg.mni_template,
        "--yes",
    ]
    if cfg.fs_license:
        cmd.extend(["--fs-license", str(Path(cfg.fs_license).expanduser())])
    if cfg.subject_jobs is not None:
        cmd.extend(["--subject-jobs", str(cfg.subject_jobs)])
    return cmd


def _build_env(cfg: FMRILocalSplitConfig, input_root: Path, output_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(cfg.env)
    env["FMRI_INPUT_ROOT"] = str(input_root)
    env["FMRI_OUTPUT_ROOT"] = str(output_root / "bids")
    env["FMRI_DERIVATIVES_ROOT"] = str(output_root / "bids" / "derivatives" / "FMRIPREP")
    if cfg.fs_license:
        env["FS_LICENSE"] = str(Path(cfg.fs_license).expanduser())
    env.setdefault("FMRI_SOURCEDATA_COPY_MODE", "auto")
    return env


def _resolve_subject_inputs(input_root: Path, subjects: list[str]) -> list[Path]:
    if not subjects:
        subject_dirs = sorted(path for path in input_root.iterdir() if path.is_dir() and path.name.startswith("sub-"))
        return subject_dirs or [input_root]
    resolved: list[Path] = []
    for subject in subjects:
        candidates = [
            input_root / subject,
            input_root / subject.removeprefix("sub-"),
            input_root / f"sub-{subject.removeprefix('sub-')}",
        ]
        match = next((path for path in candidates if path.exists() and path.is_dir()), None)
        if match is None:
            raise FileNotFoundError(f"Subject {subject!r} was not found under {input_root}")
        resolved.append(match)
    return resolved


def _resolve_derivatives_root(cfg: FMRILocalSplitConfig, input_root: Path) -> Path:
    if cfg.derivatives_root:
        return Path(cfg.derivatives_root).expanduser().resolve()
    if input_root.name == "sourcedata" and input_root.parent.name == "bids":
        return input_root.parent / "derivatives" / "FMRIPREP"
    if cfg.output_root:
        return Path(cfg.output_root).expanduser().resolve() / "bids" / "derivatives" / "FMRIPREP"
    return input_root.parent / "bids" / "derivatives" / "FMRIPREP"


def _resolve_output_root(cfg: FMRILocalSplitConfig, input_root: Path, derivatives_root: Path) -> Path:
    if cfg.output_root:
        return Path(cfg.output_root).expanduser().resolve()
    if input_root.name == "sourcedata" and input_root.parent.name == "bids":
        return input_root.parent.parent
    if derivatives_root.parts[-3:] == ("bids", "derivatives", "FMRIPREP"):
        return derivatives_root.parents[2]
    return Path("outputs/data_processing/fmri_local_split").resolve()


def _bids_subject_id(name: str) -> str:
    return name if name.startswith("sub-") else f"sub-{name}"


def _subject_qc_complete(subject_id: str, input_subject: Path, derivatives_root: Path) -> bool:
    subject_derivatives = derivatives_root / subject_id
    if not subject_derivatives.exists():
        return False
    sessions = _session_names(input_subject)
    if not sessions:
        sessions = sorted(path.name for path in subject_derivatives.glob("ses-*") if path.is_dir())
    if not sessions:
        return False
    return all(_session_qc_complete(subject_derivatives / session / "qc_statistics") for session in sessions)


def _session_names(input_subject: Path) -> list[str]:
    return sorted(path.name for path in input_subject.glob("ses-*") if path.is_dir())


def _session_qc_complete(qc_dir: Path) -> bool:
    if not qc_dir.exists() or not qc_dir.is_dir():
        return False
    required_patterns = [
        "*desc-carpetplotSignalComparison.csv",
        "*desc-carpetplot_timeseries.csv",
        "*desc-carpetplot_bold.svg",
    ]
    for pattern in required_patterns:
        matches = [path for path in qc_dir.glob(pattern) if path.is_file() and path.stat().st_size > 0]
        if not matches:
            return False
    return True
