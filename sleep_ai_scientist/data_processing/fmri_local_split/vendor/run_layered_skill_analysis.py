#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
from scipy import signal
from scipy.io import savemat


ROOT = Path(__file__).resolve().parent
SOURCE_TEST_ROOT = Path(os.environ.get("FMRI_SOURCE_TEST_ROOT", "/data"))
TEST_ROOT = Path(os.environ.get("FMRI_TEST_ROOT", SOURCE_TEST_ROOT))
INPUT_ROOT = Path(os.environ.get("FMRI_INPUT_ROOT", TEST_ROOT / "input"))
OUTPUT_ROOT = Path(os.environ.get("FMRI_OUTPUT_ROOT", "/outputs/multimodal_sleep_data/bids"))
DERIVATIVES_ROOT = Path(os.environ.get("FMRI_DERIVATIVES_ROOT", OUTPUT_ROOT / "derivatives" / "FMRIPREP"))
LOCAL_AGENT_PYTHON = Path("/opt/anaconda3/envs/agent/bin/python")
AGENT_PYTHON = Path(os.environ.get("FMRI_AGENT_PYTHON", str(LOCAL_AGENT_PYTHON if LOCAL_AGENT_PYTHON.exists() else "python")))
FMRIPREP = Path(os.environ.get("FMRIPREP_CMD", "fmriprep"))
FMRIPREP_DOCKER_IMAGE = os.environ.get("FMRIPREP_DOCKER_IMAGE", "nipreps/fmriprep:25.2.5")
FMRIPREP_FORK_RUNNER = ROOT / "run_fmriprep_fork.py"
FMRIPREP_NOMGR_RUNNER = ROOT / "run_fmriprep_nomgr.py"
FS_LICENSE = Path(os.environ.get("FS_LICENSE", ROOT / "tools" / "license.txt"))
FREESURFER_HOME = Path(os.environ.get("FREESURFER_HOME", "/usr/local/freesurfer/8.1.0"))
DCM2NIIX_CANDIDATES = [
    Path(os.environ.get("DCM2NIIX_CMD", "")),
    Path("/opt/fsl/bin/dcm2niix"),
    Path("/home/zyb/fsl/bin/dcm2niix"),
    Path("/home/zyb/fsl/pkgs/dcm2niix-1.0.20250506-hb700be7_1/bin/dcm2niix"),
    Path("/usr/local/bin/dcm2niix"),
    Path("/usr/bin/dcm2niix"),
]
START_TIME = time.monotonic()


def resolve_templateflow_home() -> Path:
    configured = os.environ.get("TEMPLATEFLOW_HOME", "").strip()
    fallback = Path.home() / ".cache" / "templateflow"
    if not configured:
        return fallback
    path = Path(configured)
    if path == Path("/templateflow") and (not path.exists() or not os.access(path, os.W_OK)):
        return fallback
    return path


TEMPLATEFLOW = resolve_templateflow_home()


def elapsed() -> str:
    seconds = int(time.monotonic() - START_TIME)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def log_step(message: str) -> None:
    print(f"[{elapsed()}] {message}", flush=True)


def finish_step(name: str, started: float) -> None:
    log_step(f"{name}: 完成，耗时 {int(time.monotonic() - started)} 秒")


@dataclass
class RunContext:
    subject: str
    input_subject: Path
    output_subject: Path
    bids_root: Path
    report: dict


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_cmd(cmd: list[str], log_path: Path, timeout: int | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=merged_env)
    write_text(
        log_path,
        "COMMAND:\n"
        + " ".join(cmd)
        + "\n\nSTDOUT:\n"
        + proc.stdout
        + "\n\nSTDERR:\n"
        + proc.stderr
        + f"\n\nRETURN_CODE: {proc.returncode}",
    )
    return proc


def run_cmd_streaming(cmd: list[str], log_path: Path, timeout: int | None = None, env: dict[str, str] | None = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    log_step("外部命令开始: " + " ".join(cmd))
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        log.write("COMMAND:\n" + " ".join(cmd) + "\n\nOUTPUT:\n")
        log.flush()
        proc = subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=merged_env, bufsize=1)
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            log.write(f"\n\nTIMEOUT_SECONDS: {timeout}\n")
            raise
        finally:
            duration = int(time.monotonic() - started)
            log.write(f"\n\nRETURN_CODE: {proc.returncode}\nDURATION_SECONDS: {duration}\n")
            log_step(f"外部命令结束: returncode={proc.returncode}, 耗时 {duration} 秒")
    return int(returncode)


def docker_mount_args(paths: list[Path]) -> list[str]:
    mounts: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        if not path:
            continue
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        mode = "ro" if resolved.is_file() else "rw"
        mounts.extend(["-v", f"{resolved}:{resolved}:{mode}"])
    return mounts


def docker_cmd(args: list[str]) -> list[str]:
    cmd = ["docker", *args]
    if os.environ.get("FMRI_USE_SG_DOCKER", "0").lower() in {"1", "true", "yes"}:
        return ["sg", "docker", "-c", shlex.join(cmd)]
    return cmd


def resolve_fmriprep_command(ctx: RunContext, fmriprep_args: list[str], fs_subjects_dir: str) -> tuple[list[str] | None, str]:
    if AGENT_PYTHON.exists():
        return [str(AGENT_PYTHON), "-m", "fmriprep", *fmriprep_args], "local-python-module"
    fmriprep_cmd = str(FMRIPREP) if FMRIPREP.exists() else shutil.which(str(FMRIPREP))
    if not fmriprep_cmd and AGENT_PYTHON.parent.exists():
        agent_fmriprep = AGENT_PYTHON.parent / "fmriprep"
        if agent_fmriprep.exists():
            fmriprep_cmd = str(agent_fmriprep)
    if fmriprep_cmd:
        return [fmriprep_cmd, *fmriprep_args], "local"

    docker_bin = shutil.which("docker")
    if not docker_bin:
        return None, f"未找到 fmriprep 可执行文件：{FMRIPREP}；同时未找到 docker，无法使用 fMRIPrep Docker 镜像 {FMRIPREP_DOCKER_IMAGE}。"

    mount_paths = [
        ctx.bids_root,
        ctx.output_subject / "fmriprep",
        FS_LICENSE,
    ]
    if fs_subjects_dir:
        mount_paths.append(Path(fs_subjects_dir))
    if TEMPLATEFLOW.exists():
        mount_paths.append(TEMPLATEFLOW)

    cmd = docker_cmd(
        [
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            *docker_mount_args(mount_paths),
            "-e",
            f"TEMPLATEFLOW_HOME={TEMPLATEFLOW}",
            "-e",
            "FSLOUTPUTTYPE=NIFTI_GZ",
            FMRIPREP_DOCKER_IMAGE,
            *fmriprep_args,
        ]
    )
    return cmd, "docker"


def ensure_dirs(ctx: RunContext) -> None:
    dirs = [
        "fmriprep/config",
        "fmriprep/output",
        "logs",
    ]
    for rel in dirs:
        (ctx.output_subject / rel).mkdir(parents=True, exist_ok=True)

    descriptions = {
        ".": "BIDS derivatives subject directory. 原始 DICOM 会先整理到 BIDS 根目录的 sourcedata 下；本目录保存该 subject 的处理结果。",
        "fmriprep": "fMRIPrep 层。这里保存 fMRIPrep 配置、运行日志和输出。若 fMRIPrep 未完成，STATUS.txt 会记录具体原因，目录仍保留。",
        "logs": "运行日志层。保存外部命令、异常堆栈和总流程报告。",
    }
    for rel, text in descriptions.items():
        write_text(ctx.output_subject / rel / "DESCRIPTION.txt", text)


def fmriprep_work_dir(ctx: RunContext) -> Path:
    configured = os.environ.get("FMRIPREP_WORK_DIR", "").strip()
    if configured:
        return Path(configured).expanduser() / ctx.subject
    return ctx.bids_root / "derivatives" / "work" / ctx.subject


def selected_session_names(subject_root: Path) -> set[str]:
    configured = os.environ.get("FMRI_SESSION_FILTER", "").strip()
    if configured:
        return {item.strip() for item in re.split(r"[,;:\s]+", configured) if item.strip()}
    sessions = find_session_dirs(subject_root)
    if sessions:
        return {path.name for path in sessions}
    sourcedata = sourcedata_subject_dir(subject_root.name)
    if sourcedata.exists():
        return {path.name for path in find_session_dirs(sourcedata)}
    raw_sessions = find_raw_session_dirs(subject_root)
    start = int(os.environ.get("FMRI_RAW_SESSION_START", "0"))
    return {f"ses-mri{idx + start}" for idx, _ in enumerate(raw_sessions)}


def surface_recon_backend() -> str:
    configured = os.environ.get("FMRI_SURFACE_RECON_BACKEND", os.environ.get("FMRI_RECON_BACKEND", "freesurfer")).strip().lower()
    aliases = {
        "fs": "freesurfer",
        "free": "freesurfer",
        "freesurfer": "freesurfer",
        "fast": "fastsurfer",
        "fastsurfer": "fastsurfer",
    }
    backend = aliases.get(configured, configured)
    if backend not in {"freesurfer", "fastsurfer"}:
        raise ValueError(f"不支持的 surface recon backend: {configured}; 仅支持 freesurfer 或 fastsurfer")
    return backend


def default_fs_subjects_dir(ctx: RunContext, backend: str | None = None) -> Path:
    resolved_backend = backend or surface_recon_backend()
    if resolved_backend == "freesurfer":
        return ctx.bids_root / "derivatives" / "FREESURFER"
    if resolved_backend == "fastsurfer":
        return ctx.bids_root / "derivatives" / "FASTSURFER"
    return ctx.output_subject / "fmriprep" / "output" / "sourcedata" / resolved_backend


def configured_fs_subjects_dir(ctx: RunContext, backend: str | None = None) -> Path:
    configured = os.environ.get("FMRI_FS_SUBJECTS_DIR", "").strip()
    if configured:
        return Path(configured)
    return default_fs_subjects_dir(ctx, backend)


def recon_subject_candidates(ctx: RunContext, backend: str | None = None) -> list[Path]:
    backend = backend or surface_recon_backend()
    candidates = [default_fs_subjects_dir(ctx, backend)]
    configured = os.environ.get("FMRI_FS_SUBJECTS_DIR", "").strip()
    if configured:
        candidates.insert(0, Path(configured))
    seen: set[Path] = set()
    unique = []
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def find_recon_subject_dir(ctx: RunContext, backend: str | None = None) -> Path | None:
    names = [ctx.subject, *sorted(p.name for p in default_fs_subjects_dir(ctx, backend or surface_recon_backend()).glob(f"{ctx.subject}*"))]
    for subjects_dir in recon_subject_candidates(ctx, backend):
        for name in names:
            candidate = subjects_dir / name
            if candidate.exists():
                return candidate
        matches = sorted(path for path in subjects_dir.glob(f"{ctx.subject}*") if path.is_dir())
        if matches:
            return matches[0]
    return None


def recon_subject_is_complete(subject_dir: Path | None) -> bool:
    if not subject_dir:
        return False
    required = [
        subject_dir / "surf" / "lh.white",
        subject_dir / "surf" / "rh.white",
        subject_dir / "surf" / "lh.pial",
        subject_dir / "surf" / "rh.pial",
    ]
    return all(path.exists() and path.stat().st_size > 0 for path in required)


def missing_recon_surface_files(subject_dir: Path | None) -> list[str]:
    if not subject_dir:
        return []
    required = [
        subject_dir / "surf" / "lh.white",
        subject_dir / "surf" / "rh.white",
        subject_dir / "surf" / "lh.pial",
        subject_dir / "surf" / "rh.pial",
    ]
    return [str(path) for path in required if not path.exists() or path.stat().st_size <= 0]


def usable_fs_subjects_dir(ctx: RunContext, backend: str) -> tuple[str, dict[str, str | bool]]:
    subject_dir = find_recon_subject_dir(ctx, backend)
    complete = recon_subject_is_complete(subject_dir)
    subjects_dir = str(subject_dir.parent) if complete and subject_dir else ""
    return subjects_dir, {
        "surface_recon_backend": backend,
        "recon_subject_dir": str(subject_dir) if subject_dir else "",
        "fs_subjects_dir": subjects_dir,
        "complete": complete,
    }


def fmriprep_managed_recon_subject_dir(ctx: RunContext, backend: str | None = None) -> Path:
    return default_fs_subjects_dir(ctx, backend or surface_recon_backend()) / ctx.subject


def recon_all_running_for_subject(ctx: RunContext) -> bool:
    try:
        proc = subprocess.run(["ps", "-eo", "pid=,cmd="], text=True, capture_output=True, check=False)
    except Exception:
        return True
    if proc.returncode != 0:
        return True
    subject_tokens = {
        ctx.subject,
        str(fmriprep_managed_recon_subject_dir(ctx, "freesurfer")),
        str(fmriprep_managed_recon_subject_dir(ctx, "fastsurfer")),
    }
    for line in proc.stdout.splitlines():
        if "recon-all" not in line:
            continue
        if any(token and token in line for token in subject_tokens):
            return True
    return False


def cleanup_stale_freesurfer_locks(ctx: RunContext) -> dict[str, Any]:
    lock_dirs = [
        fmriprep_managed_recon_subject_dir(ctx, "freesurfer") / "scripts",
        fmriprep_managed_recon_subject_dir(ctx, "fastsurfer") / "scripts",
    ]
    locks: list[Path] = []
    for lock_dir in lock_dirs:
        locks.extend(sorted(path for path in lock_dir.glob("IsRunning*") if path.is_file()))
    status: dict[str, Any] = {
        "found": [str(path) for path in locks],
        "removed": [],
        "skipped": False,
        "reason": "",
    }
    if not locks:
        status["reason"] = "未发现 FreeSurfer IsRunning 锁文件。"
        return status
    if os.environ.get("FMRIPREP_CLEAN_STALE_ISR", "1") != "1":
        status["skipped"] = True
        status["reason"] = "FMRIPREP_CLEAN_STALE_ISR=0，保留 IsRunning 锁文件。"
        return status
    if recon_all_running_for_subject(ctx):
        status["skipped"] = True
        status["reason"] = "检测到该 subject 可能仍有 recon-all 正在运行，保留 IsRunning 锁文件。"
        return status
    for lock in locks:
        try:
            lock.unlink()
            status["removed"].append(str(lock))
        except FileNotFoundError:
            continue
        except OSError as exc:
            status["skipped"] = True
            status["reason"] = f"删除 {lock} 失败: {type(exc).__name__}: {exc}"
            break
    if not status["reason"]:
        status["reason"] = "已清理上次中断遗留的 FreeSurfer IsRunning 锁文件。"
    return status


def quarantine_incomplete_freesurfer_subject(ctx: RunContext, backend: str | None = None) -> dict[str, Any]:
    backend = backend or surface_recon_backend()
    subject_dir = find_recon_subject_dir(ctx, backend) or fmriprep_managed_recon_subject_dir(ctx, backend)
    status: dict[str, Any] = {
        "surface_recon_backend": backend,
        "subject_dir": str(subject_dir),
        "exists": subject_dir.exists(),
        "complete": False,
        "missing": [],
        "moved_to": "",
        "skipped": False,
        "reason": "",
    }
    if not subject_dir.exists():
        status["reason"] = "未发现 fMRIPrep 管理的 FreeSurfer subject 目录。"
        return status
    status["complete"] = recon_subject_is_complete(subject_dir)
    status["missing"] = missing_recon_surface_files(subject_dir)
    if status["complete"]:
        status["reason"] = "FreeSurfer subject 已包含完整 lh/rh white/pial surface。"
        return status
    if os.environ.get("FMRIPREP_QUARANTINE_INCOMPLETE_FS", "1") != "1":
        status["skipped"] = True
        status["reason"] = "FMRIPREP_QUARANTINE_INCOMPLETE_FS=0，保留不完整 FreeSurfer 目录。"
        return status
    if recon_all_running_for_subject(ctx):
        status["skipped"] = True
        status["reason"] = "检测到该 subject 可能仍有 recon-all 正在运行，保留不完整 FreeSurfer 目录。"
        return status
    suffix = time.strftime("%Y%m%d-%H%M%S")
    backup = subject_dir.with_name(f"{subject_dir.name}.incomplete-{suffix}")
    counter = 1
    while backup.exists():
        backup = subject_dir.with_name(f"{subject_dir.name}.incomplete-{suffix}-{counter}")
        counter += 1
    try:
        shutil.move(str(subject_dir), str(backup))
    except OSError as exc:
        status["skipped"] = True
        status["reason"] = f"隔离不完整 FreeSurfer 目录失败: {type(exc).__name__}: {exc}"
        return status
    status["moved_to"] = str(backup)
    status["reason"] = "已隔离不完整 FreeSurfer subject 目录；下一次 fMRIPrep 将重新生成该 subject 的 FreeSurfer 输出。"
    return status


def ensure_session_analysis_dirs(ctx: RunContext, session: str) -> None:
    descriptions = {
        "clean_data": "去噪后的 BOLD/surface 数据。",
        "clean_data_regressor": "Nuisance regressors 层。保存 motion/csf/wm/CompCor/PCA 及其组合回归器。",
        "clean_data_regressor_stat": "FD/DVARS 与 bad epoch 层。保存 FD/DVARS 数值、阈值和 bad epoch 标记。",
        "clean_info": "去噪和 bad epoch 信息。",
        "figures": "该 session 的 fMRIPrep reportlet 图层，包括 carpetplot、bbregister、confounds 等 SVG/HTML。",
        "surface_transform": "Volume 到 surface 与 surface mask 层。依赖 fMRIPrep/FreeSurfer surface 输出。",
        "segment": "分段层。volume/surface 分开放置；surface 按 W_0-W_12、S_0-S_3 与左右半球保存。",
        "time_frequency": "时频分析层。保存 PSD、ALFF、fALFF 等结果。",
        "qc_statistics": "所选 session 的 QC 图和统计摘要。",
    }
    for rel, text in descriptions.items():
        write_text(ctx.output_subject / session / rel / "DESCRIPTION.txt", text)


def prune_legacy_top_level_dirs(ctx: RunContext) -> None:
    if os.environ.get("FMRI_PRUNE_LEGACY_TOP_DIRS", "1") != "1":
        return
    keep = {"fmriprep", "logs", *selected_session_names(ctx.input_subject)}
    legacy = {
        "clean_data",
        "clean_data_regressor",
        "clean_data_regressor_stat",
        "clean_info",
        "confounds",
        "dicom_conversion",
        "figures",
        "qc_statistics",
        "segment",
        "surface_transform",
        "time_frequency",
    }
    removed = []
    for path in sorted(ctx.output_subject.iterdir()) if ctx.output_subject.exists() else []:
        if path.is_dir() and path.name in legacy and path.name not in keep:
            shutil.rmtree(path)
            removed.append(path.name)
    if removed:
        write_text(ctx.output_subject / "logs" / "pruned_legacy_top_dirs.txt", "\n".join(removed))


def bids_subject_id(subject_folder: str) -> str:
    return subject_folder if subject_folder.startswith("sub-") else f"sub-{subject_folder}"


def sourcedata_subject_dir(subject: str) -> Path:
    return OUTPUT_ROOT / "sourcedata" / bids_subject_id(subject)


def classify_raw_series(series_name: str) -> str | None:
    lower = series_name.lower()
    if any(token in lower for token in ["scout", "localizer", "phoenix", "report"]):
        return None
    if any(token in lower for token in ["field", "fieldmap", "field_mapping", "gre_field", "b0_pa", "b0_ap", "b0_auto"]):
        return "fmap"
    if "bold" in lower or ("ep2d" in lower and "diff" not in lower):
        return "func"
    if any(token in lower for token in ["diff", "dti", "dwi", "resolve", "adc", "tracew"]):
        return "dwi"
    if any(token in lower for token in ["t1", "t2", "mprage", "spc", "flair", "qtse"]):
        return "anat"
    return None


def dicom_file_count(path: Path) -> int:
    return sum(1 for _ in path.glob("*.dcm"))


def has_dicom_files(path: Path) -> bool:
    return any(path.glob("*.dcm"))


def find_raw_series_dirs(raw_session: Path) -> list[Path]:
    direct = sorted(path for path in raw_session.iterdir() if path.is_dir())
    direct_with_dicom = [path for path in direct if has_dicom_files(path)]
    if direct_with_dicom:
        return direct_with_dicom
    return sorted(path for path in raw_session.rglob("*") if path.is_dir() and has_dicom_files(path))


def find_raw_session_dirs(subject_root: Path) -> list[Path]:
    if find_session_dirs(subject_root):
        return []
    raw_root = subject_root / "mri" if (subject_root / "mri").is_dir() else subject_root
    sessions = []
    for candidate in sorted(raw_root.iterdir()):
        if not candidate.is_dir() or candidate.name.startswith(".") or candidate.name.startswith("ses-"):
            continue
        child_dirs = [path for path in candidate.iterdir() if path.is_dir()]
        if any(has_dicom_files(path) for path in child_dirs):
            sessions.append(candidate)
        elif any(has_dicom_files(path) for path in candidate.rglob("*") if path.is_dir()):
            sessions.append(candidate)
    if sessions:
        return sessions
    if any(has_dicom_files(path) for path in raw_root.iterdir() if path.is_dir()):
        return [raw_root]
    if any(has_dicom_files(path) for path in raw_root.rglob("*") if path.is_dir()):
        return [raw_root]
    return []


def copy_raw_dicom_file(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    mode = os.environ.get("FMRI_SOURCEDATA_COPY_MODE", "auto").strip().lower()
    if mode == "symlink":
        dst.symlink_to(src)
        return
    if mode in {"auto", "hardlink", "link"}:
        try:
            os.link(src, dst)
            return
        except OSError:
            if mode in {"hardlink", "link"}:
                raise
    shutil.copy2(src, dst)


def mirror_series_to_sourcedata(src_series: Path, dst_series: Path) -> int:
    dcm_files = sorted(src_series.glob("*.dcm"))
    if not dcm_files:
        return 0
    existing = dicom_file_count(dst_series)
    if existing == len(dcm_files):
        return existing
    dst_series.mkdir(parents=True, exist_ok=True)
    for src in dcm_files:
        copy_raw_dicom_file(src, dst_series / src.name)
    return dicom_file_count(dst_series)


def prepare_sourcedata(ctx: RunContext) -> Path:
    dst_subject = ctx.bids_root / "sourcedata" / ctx.subject
    direct_sessions = find_session_dirs(ctx.input_subject)
    raw_sessions = find_raw_session_dirs(ctx.input_subject)
    manifest: dict[str, object] = {"subject": ctx.subject, "input": str(ctx.input_subject), "sessions": []}

    if direct_sessions:
        for ses in direct_sessions:
            if ses.name not in selected_session_names(ctx.input_subject):
                continue
            for category in ["anat", "dwi", "fmap", "func"]:
                src_category = ses / category
                if not src_category.is_dir():
                    continue
                for src_series in sorted(path for path in src_category.iterdir() if path.is_dir()):
                    count = mirror_series_to_sourcedata(src_series, dst_subject / ses.name / category / src_series.name)
                    if count:
                        manifest["sessions"].append({"session": ses.name, "category": category, "series": src_series.name, "dicom_count": count})
    elif raw_sessions:
        allowed = selected_session_names(ctx.input_subject)
        for idx, raw_session in enumerate(raw_sessions):
            ses_name = f"ses-mri{idx + int(os.environ.get('FMRI_RAW_SESSION_START', '0'))}"
            if allowed and ses_name not in allowed:
                continue
            for src_series in find_raw_series_dirs(raw_session):
                category = classify_raw_series(src_series.name)
                if not category:
                    continue
                count = mirror_series_to_sourcedata(src_series, dst_subject / ses_name / category / src_series.name)
                if count:
                    manifest["sessions"].append(
                        {
                            "session": ses_name,
                            "raw_session": raw_session.name,
                            "category": category,
                            "series": src_series.name,
                            "dicom_count": count,
                        }
                    )

    if manifest["sessions"]:
        write_json(dst_subject / "sourcedata_manifest.json", manifest)
        ctx.report["sourcedata"] = manifest
        return dst_subject
    return ctx.input_subject


def find_session_dirs(subject_root: Path) -> list[Path]:
    direct = sorted(path for path in subject_root.iterdir() if path.is_dir() and path.name.startswith("ses-"))
    if direct:
        return direct
    sessions = []
    for path in sorted(subject_root.rglob("ses-*")):
        if not path.is_dir() or any(part.startswith(".") for part in path.parts):
            continue
        if any(parent.name.startswith("ses-") for parent in path.parents if parent != path):
            continue
        if (path / "anat").is_dir() or (path / "func").is_dir():
            sessions.append(path)
    return sessions


def subject_has_imaging_data(subject_root: Path) -> bool:
    for ses in find_session_dirs(subject_root):
        if list(ses.glob("func/**/*.nii")) or list(ses.glob("func/**/*.nii.gz")) or list(ses.glob("func/**/*.dcm")):
            return True
        if list(ses.glob("anat/**/*.nii")) or list(ses.glob("anat/**/*.nii.gz")) or list(ses.glob("anat/**/*.dcm")):
            return True
    for raw_session in find_raw_session_dirs(subject_root):
        for series in find_raw_series_dirs(raw_session):
            if classify_raw_series(series.name) and has_dicom_files(series):
                return True
    return False


def choose_subject() -> tuple[str, Path]:
    requested = os.environ.get("FMRI_SUBJECT")
    subjects = sorted(path for path in INPUT_ROOT.iterdir() if path.is_dir() and not path.name.startswith("."))
    if not subjects:
        raise FileNotFoundError(f"没有在 {INPUT_ROOT} 下找到被试目录")
    if requested:
        candidates = [
            INPUT_ROOT / requested,
            INPUT_ROOT / requested.removeprefix("sub-"),
            INPUT_ROOT / bids_subject_id(requested),
        ]
        requested_path = next((path for path in candidates if path.exists() and path.is_dir()), None)
        if requested_path is None:
            requested_path = INPUT_ROOT / requested
        if not requested_path.exists():
            raise FileNotFoundError(f"指定被试不存在：{requested_path}")
        return bids_subject_id(requested_path.name), requested_path
    for subject in subjects:
        if subject_has_imaging_data(subject):
            return bids_subject_id(subject.name), subject
    return bids_subject_id(subjects[0].name), subjects[0]


def copy_or_gzip_nii(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.name.endswith(".nii.gz"):
        shutil.copyfile(src, dst)
    elif src.suffix == ".nii" and dst.name.endswith(".nii.gz"):
        with src.open("rb") as f_in, gzip.open(dst, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    else:
        shutil.copyfile(src, dst)


def find_nifti(series_dir: Path) -> list[Path]:
    return sorted([*series_dir.glob("*.nii"), *series_dir.glob("*.nii.gz")])


def find_json_for(nii: Path) -> Path | None:
    stem = nii.name
    if stem.endswith(".nii.gz"):
        stem = stem[:-7]
    elif stem.endswith(".nii"):
        stem = stem[:-4]
    candidate = nii.with_name(stem + ".json")
    if candidate.exists():
        return candidate
    jsons = sorted(nii.parent.glob("*.json"))
    return jsons[0] if jsons else None


def resolve_dcm2niix() -> str | None:
    configured = os.environ.get("DCM2NIIX_CMD", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
        found = shutil.which(configured)
        if found:
            return found
    found = shutil.which("dcm2niix")
    if found:
        return found
    for path in DCM2NIIX_CANDIDATES:
        if str(path) and path.exists() and os.access(path, os.X_OK):
            return str(path)
    return None


def convert_dicom_series_to_bids(series_dir: Path, out_dir: Path, bids_stem: str, ctx: RunContext) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "STATUS.txt"
    expected = out_dir / f"{bids_stem}.nii.gz"
    if expected.exists():
        if status_path.exists():
            status_path.unlink()
        return expected
    dcm_files = list(series_dir.glob("*.dcm"))
    if not dcm_files:
        return None
    dcm2niix = resolve_dcm2niix()
    if not dcm2niix:
        write_text(status_path, "未找到 dcm2niix，无法从 DICOM 转换 NIfTI。")
        return None
    proc = run_cmd(
        [dcm2niix, "-z", "y", "-f", bids_stem, "-o", str(out_dir), str(series_dir)],
        ctx.output_subject / "logs" / f"dcm2niix_{series_dir.name}.log",
        timeout=600,
    )
    if proc.returncode != 0:
        write_text(status_path, f"dcm2niix 失败，返回码 {proc.returncode}。详见 logs。")
        return None
    candidates = sorted(out_dir.glob(f"{bids_stem}*.nii.gz")) + sorted(out_dir.glob(f"{bids_stem}*.nii"))
    exact = [path for path in candidates if path.name in {f"{bids_stem}.nii.gz", f"{bids_stem}.nii"}]
    if candidates and status_path.exists():
        status_path.unlink()
    return (exact or candidates or [None])[0]


def prepare_bids(ctx: RunContext) -> tuple[list[Path], list[Path]]:
    bids = ctx.bids_root
    (bids / ctx.subject).mkdir(parents=True, exist_ok=True)
    write_json(bids / "dataset_description.json", {"Name": "Local fMRI skill analysis", "BIDSVersion": "1.8.0"})
    write_json(bids / "derivatives" / "dataset_description.json", {"Name": "Local fMRI skill analysis derivatives", "BIDSVersion": "1.8.0"})
    write_json(bids / "derivatives" / "FMRIPREP" / "dataset_description.json", {"Name": "FMRIPREP", "BIDSVersion": "1.8.0"})
    input_subject = prepare_sourcedata(ctx)

    bold_outputs: list[Path] = []
    anat_outputs: list[Path] = []
    allowed_sessions = selected_session_names(input_subject)
    sessions = [ses for ses in find_session_dirs(input_subject) if not allowed_sessions or ses.name in allowed_sessions]
    if not sessions:
        raise FileNotFoundError(f"没有找到可处理 session：{sorted(allowed_sessions)}")
    fast_single = os.environ.get("FMRI_FAST_SINGLE", "0") == "1"
    include_t2 = os.environ.get("FMRI_INCLUDE_T2", "1") == "1"
    max_bold_runs = int(os.environ.get("FMRI_MAX_BOLD_RUNS", "999"))
    for ses_index, ses in enumerate(sessions):
        ensure_session_analysis_dirs(ctx, ses.name)
        ses_out = bids / ctx.subject / ses.name
        anat_out = ses_out / "anat"
        func_out = ses_out / "func"
        anat_out.mkdir(parents=True, exist_ok=True)
        func_out.mkdir(parents=True, exist_ok=True)

        anat_series = sorted((ses / "anat").iterdir()) if (ses / "anat").exists() else []
        t1_count = 0
        t2_count = 0
        for series in [p for p in anat_series if p.is_dir()]:
            lower = series.name.lower()
            if "t2" in lower:
                if not include_t2:
                    continue
                t2_count += 1
                suffix = "T2w"
                run = t2_count
            else:
                if fast_single and t1_count >= 1:
                    continue
                t1_count += 1
                suffix = "T1w"
                run = t1_count
            run_part = f"_run-{run:02d}" if run > 1 else ""
            bids_stem = f"{ctx.subject}_{ses.name}{run_part}_{suffix}"
            dst = anat_out / f"{bids_stem}.nii.gz"
            niftis = find_nifti(series)
            if niftis:
                nii = niftis[0]
                copy_or_gzip_nii(nii, dst)
                src_json = find_json_for(nii)
                if src_json:
                    shutil.copyfile(src_json, dst.with_suffix("").with_suffix(".json"))
            else:
                converted = convert_dicom_series_to_bids(series, anat_out, bids_stem, ctx)
                if not converted:
                    continue
                dst = converted
            anat_outputs.append(dst)

        func_series = sorted((ses / "func").iterdir()) if (ses / "func").exists() else []
        for idx, series in enumerate([p for p in func_series if p.is_dir()], start=1):
            if idx > max_bold_runs:
                continue
            task = f"sleep{ses_index if len(func_series) == 1 else idx - 1}"
            bids_stem = f"{ctx.subject}_{ses.name}_task-{task}_run-{idx:02d}_bold"
            dst = func_out / f"{bids_stem}.nii.gz"
            niftis = find_nifti(series)
            meta = {}
            if niftis:
                nii = niftis[0]
                copy_or_gzip_nii(nii, dst)
                src_json = find_json_for(nii)
                if src_json:
                    try:
                        meta = json.loads(src_json.read_text(encoding="utf-8"))
                    except Exception:
                        meta = {}
            else:
                converted = convert_dicom_series_to_bids(series, func_out, bids_stem, ctx)
                if not converted:
                    continue
                dst = converted
                src_json = find_json_for(dst)
                if src_json:
                    try:
                        meta = json.loads(src_json.read_text(encoding="utf-8"))
                    except Exception:
                        meta = {}
            bold_outputs.append(dst)
            meta["TaskName"] = task
            write_json(dst.with_suffix("").with_suffix(".json"), meta)

    write_text(
        ctx.output_subject / "fmriprep" / "config" / "bids_status.txt",
        f"已整理 BIDS 数据：session {', '.join(ses.name for ses in sessions)}；解剖 NIfTI {len(anat_outputs)} 个，功能 BOLD NIfTI {len(bold_outputs)} 个。支持多个输入序列，使用 run-XX 编号。",
    )
    ctx.report["bids"] = {"anat_files": [str(p) for p in anat_outputs], "bold_files": [str(p) for p in bold_outputs]}
    return anat_outputs, bold_outputs


def parse_output_spaces() -> list[str]:
    return os.environ.get("FMRIPREP_OUTPUT_SPACES", "T1w MNI152NLin6Asym:res-2 MNI152NLin2009cAsym:res-2 fsnative fsaverage").split()


def template_requirements(output_spaces: list[str]) -> dict[str, list[str]]:
    required: dict[str, list[str]] = {}
    for space in output_spaces:
        if space == "T1w" or space.startswith("fs"):
            continue
        parts = space.split(":")
        template = parts[0]
        res = "02"
        for part in parts[1:]:
            if part.startswith("res-"):
                value = part.removeprefix("res-")
                res = value.zfill(2) if value.isdigit() else value
        required.setdefault(template, [])
        required[template].extend([
            f"tpl-{template}_res-{res}_T1w.nii.gz",
            f"tpl-{template}_res-{res}_desc-brain_mask.nii.gz",
        ])
    return required


def inspect_templateflow(ctx: RunContext, output_spaces: list[str]) -> dict:
    package_tpl = Path(os.environ.get("TEMPLATEFLOW_PACKAGE_DIR", "/opt/conda/lib/python3.11/site-packages/templateflow"))
    required = template_requirements(output_spaces)
    status = {
        "说明": (
            "fMRIPrep 通过 TEMPLATEFLOW_HOME 读取模板缓存。"
            "site-packages/templateflow 是 Python 包目录，通常只包含客户端代码和骨架文件，不等价于模板数据缓存。"
        ),
        "output_spaces": output_spaces,
        "site_packages_templateflow": {
            "path": str(package_tpl),
            "nifti_or_h5_files": sorted(str(p) for p in package_tpl.rglob("*") if p.suffix in {".h5"} or p.name.endswith(".nii.gz")),
        },
        "required_files": {},
    }
    for template, names in required.items():
        local_tpl = ROOT / "core" / "mri" / f"tpl-{template}"
        cache_tpl = TEMPLATEFLOW / f"tpl-{template}"
        for name in names:
            entries = {}
            for label, base in [("core_mri_tpl", local_tpl), ("templateflow_cache", cache_tpl)]:
                path = base / name
                exists = path.exists()
                real_exists = path.resolve().exists() if exists else False
                size = path.resolve().stat().st_size if real_exists else 0
                entries[label] = {"path": str(path), "exists": exists, "target_exists": real_exists, "size": size}
            status["required_files"][name] = entries
    write_json(ctx.output_subject / "fmriprep" / "config" / "templateflow_local_check.json", status)
    return status


def attempt_fmriprep(ctx: RunContext) -> dict:
    status = {"attempted": False, "returncode": None, "reason": ""}
    output_spaces = parse_output_spaces()
    try:
        TEMPLATEFLOW.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        status["reason"] = f"TEMPLATEFLOW_HOME 不可写：{TEMPLATEFLOW}。请设置到可写目录，例如 /home/zyb/.cache/templateflow。"
        write_text(ctx.output_subject / "fmriprep" / "STATUS.txt", status["reason"])
        return status
    inspect_templateflow(ctx, output_spaces)
    reusable = reusable_fmriprep_outputs(ctx)
    if reusable["complete"]:
        status.update(
            {
                "attempted": False,
                "returncode": 0,
                "reason": "检测到所需 session 已有完整 fMRIPrep/FreeSurfer 输出，跳过重复 fMRIPrep。",
                "reused": True,
                "sessions": reusable["sessions"],
            }
        )
        write_text(ctx.output_subject / "fmriprep" / "STATUS.txt", status["reason"])
        write_json(ctx.output_subject / "fmriprep" / "config" / "fmriprep_reuse_status.json", reusable)
        return status
    nthreads = os.environ.get("FMRIPREP_NTHREADS", "8")
    omp_nthreads = os.environ.get("FMRIPREP_OMP_NTHREADS", "2")
    mem_mb = os.environ.get("FMRIPREP_MEM_MB", "48000")
    timeout = int(os.environ.get("FMRIPREP_TIMEOUT", "21600"))
    direct_cli = os.environ.get("FMRIPREP_DIRECT_CLI", "1") == "1"
    recon_backend = surface_recon_backend()
    fs_no_reconall = os.environ.get("FMRIPREP_FS_NO_RECONALL", "0") == "1" or recon_backend == "fastsurfer"
    no_msm = os.environ.get("FMRIPREP_NO_MSM", "1") != "0"
    track_sessions = os.environ.get("FMRIPREP_TRACK_SESSIONS", "0") == "1"
    fs_lock_cleanup = cleanup_stale_freesurfer_locks(ctx)
    status["fs_lock_cleanup"] = fs_lock_cleanup
    write_json(ctx.output_subject / "fmriprep" / "config" / "freesurfer_isrunning_cleanup.json", fs_lock_cleanup)
    if fs_lock_cleanup.get("skipped") and fs_lock_cleanup.get("found"):
        status["reason"] = str(fs_lock_cleanup.get("reason") or "检测到 FreeSurfer IsRunning 锁文件，未启动 fMRIPrep。")
        write_text(ctx.output_subject / "fmriprep" / "STATUS.txt", status["reason"])
        return status
    fs_subject_quarantine = quarantine_incomplete_freesurfer_subject(ctx, recon_backend)
    status["fs_subject_quarantine"] = fs_subject_quarantine
    write_json(ctx.output_subject / "fmriprep" / "config" / "freesurfer_incomplete_subject_cleanup.json", fs_subject_quarantine)
    if fs_subject_quarantine.get("skipped") and fs_subject_quarantine.get("exists") and not fs_subject_quarantine.get("complete"):
        status["reason"] = str(fs_subject_quarantine.get("reason") or "检测到不完整 FreeSurfer subject 目录，未启动 fMRIPrep。")
        write_text(ctx.output_subject / "fmriprep" / "STATUS.txt", status["reason"])
        return status
    fs_subjects_dir, fs_reuse = usable_fs_subjects_dir(ctx, recon_backend)
    if recon_backend == "fastsurfer" and not fs_subjects_dir:
        status["reason"] = "FastSurfer 模式需要完整的预计算 surface，但未在 BIDS derivatives/FASTSURFER 下找到包含 lh/rh white/pial 的 subject 目录。请先运行 FastSurfer，或切换到 FreeSurfer 模式。"
        status["surface_recon_backend"] = recon_backend
        status["fs_reuse"] = fs_reuse
        write_text(ctx.output_subject / "fmriprep" / "STATUS.txt", status["reason"])
        write_json(ctx.output_subject / "fmriprep" / "config" / "fmriprep_fs_reuse_status.json", fs_reuse)
        return status
    skull_strip_template = os.environ.get("FMRIPREP_SKULL_STRIP_TEMPLATE", "").strip()
    work_dir = fmriprep_work_dir(ctx)
    work_dir.mkdir(parents=True, exist_ok=True)
    configured_fs_root = os.environ.get("FMRI_FS_SUBJECTS_DIR", "").strip()
    fmriprep_fs_subjects_dir = fs_subjects_dir
    if not fmriprep_fs_subjects_dir and recon_backend == "freesurfer":
        fmriprep_fs_subjects_dir = str(
            Path(configured_fs_root).expanduser() if configured_fs_root else default_fs_subjects_dir(ctx, recon_backend)
        )
    runtime_subjects_dir = Path(fmriprep_fs_subjects_dir) if fmriprep_fs_subjects_dir else default_fs_subjects_dir(ctx, recon_backend)
    runtime_subjects_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        ctx.output_subject / "fmriprep" / "config" / "work_dir.json",
        {
            "work_dir": str(work_dir),
            "bids_root": str(ctx.bids_root),
            "subjects_dir": str(runtime_subjects_dir),
            "inside_bids_root": str(work_dir).startswith(str(ctx.bids_root)),
        },
    )
    fmriprep_args = [
        str(ctx.bids_root),
        str(ctx.output_subject / "fmriprep" / "output"),
        "participant",
        "--participant-label",
        ctx.subject.replace("sub-", ""),
        "--skip-bids-validation",
        "--fs-license-file",
        str(FS_LICENSE),
        "--output-spaces",
        *output_spaces,
        "--ignore",
        "slicetiming",
        "--nthreads",
        nthreads,
        "--omp-nthreads",
        omp_nthreads,
        "--mem",
        mem_mb,
        "--work-dir",
        str(work_dir),
        "--stop-on-first-crash",
    ]
    fmriprep_args.append("--track-sessions" if track_sessions else "--no-track-sessions")
    if fs_no_reconall:
        fmriprep_args.insert(fmriprep_args.index("--output-spaces"), "--fs-no-reconall")
    if fmriprep_fs_subjects_dir:
        fmriprep_args[fmriprep_args.index("--output-spaces"):fmriprep_args.index("--output-spaces")] = [
            "--fs-subjects-dir",
            fmriprep_fs_subjects_dir,
        ]
        if fs_subjects_dir:
            fmriprep_args.insert(fmriprep_args.index("--output-spaces"), "--fs-no-resume")
    if fs_subjects_dir:
        if os.environ.get("FMRIPREP_CLEAN_WORKDIR_ON_FASTSURFER", "0") == "1":
            fmriprep_args.append("--clean-workdir")
    if no_msm:
        fmriprep_args.insert(fmriprep_args.index("--output-spaces"), "--no-msm")
    if skull_strip_template:
        fmriprep_args.extend(["--skull-strip-template", skull_strip_template])
    if direct_cli:
        cmd, backend = resolve_fmriprep_command(ctx, fmriprep_args, fs_subjects_dir)
    else:
        cmd = [str(AGENT_PYTHON), str(FMRIPREP_NOMGR_RUNNER), *fmriprep_args]
        backend = "local-runner"
    if not cmd:
        status["reason"] = backend
        write_text(ctx.output_subject / "fmriprep" / "STATUS.txt", status["reason"])
        return status
    path_entries = []
    if AGENT_PYTHON.parent.exists():
        path_entries.append(str(AGENT_PYTHON.parent))
    if (FREESURFER_HOME / "bin").exists():
        path_entries.append(str(FREESURFER_HOME / "bin"))
    path_entries.append(os.environ.get("PATH", ""))
    ld_library_entries = []
    if (FREESURFER_HOME / "lib").exists():
        ld_library_entries.append(str(FREESURFER_HOME / "lib"))
    ld_library_entries.append(os.environ.get("LD_LIBRARY_PATH", ""))
    env = {
        "PATH": os.pathsep.join(entry for entry in path_entries if entry),
        "LD_LIBRARY_PATH": os.pathsep.join(entry for entry in ld_library_entries if entry),
        "MPLCONFIGDIR": "/tmp/matplotlib",
        "TEMPLATEFLOW_HOME": str(TEMPLATEFLOW),
        "FREESURFER_HOME": str(FREESURFER_HOME),
        "FREESURFER": str(FREESURFER_HOME),
        "SUBJECTS_DIR": str(runtime_subjects_dir),
        "FSLOUTPUTTYPE": "NIFTI_GZ",
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "1"),
        "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS", "1"),
        "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS", "1"),
        "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS": os.environ.get("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS", "1"),
        "NUMEXPR_NUM_THREADS": os.environ.get("NUMEXPR_NUM_THREADS", "1"),
        "VECLIB_MAXIMUM_THREADS": os.environ.get("VECLIB_MAXIMUM_THREADS", "1"),
    }
    status["attempted"] = True
    try:
        returncode = run_cmd_streaming(cmd, ctx.output_subject / "logs" / "fmriprep_attempt.log", timeout=timeout, env=env)
        status["returncode"] = returncode
        if returncode == 0:
            status["reason"] = "fMRIPrep 成功完成。"
        else:
            status["reason"] = "fMRIPrep 未成功完成。详见 logs/fmriprep_attempt.log；若日志仍指向 TemplateFlow，则需要继续补齐对应模板实体。"
            if no_msm:
                status["reason"] += " 本地默认已启用 --no-msm，以避开当前 FSL msm 与 sMRIPrep MSM 配置的参数兼容问题。"
    except subprocess.TimeoutExpired:
        status["reason"] = f"fMRIPrep 运行超过 {timeout} 秒被停止；目录保留，详见日志。"
    write_text(ctx.output_subject / "fmriprep" / "STATUS.txt", status["reason"])
    write_json(
        ctx.output_subject / "fmriprep" / "config" / "fmriprep_command.json",
        {
            "command": cmd,
            "backend": backend,
            "docker_image": FMRIPREP_DOCKER_IMAGE if backend == "docker" else "",
            "surface_recon_backend": recon_backend,
            "track_sessions": track_sessions,
            "no_msm": no_msm,
            "fs_subjects_dir": fs_subjects_dir,
            "fs_reuse": fs_reuse,
            "fs_lock_cleanup": fs_lock_cleanup,
            "fs_subject_quarantine": fs_subject_quarantine,
            "reason": "当前环境默认使用 --no-msm 和 --no-track-sessions，避免生成 ses-mri0-mri1 这类组合 session 目录。FreeSurfer 模式始终传入 --fs-subjects-dir，将每个被试的 FreeSurfer 结果统一保存到 BIDS derivatives/FREESURFER；只有检测到完整 lh/rh white/pial surface 时才额外传入 --fs-no-resume 复用既有结果。启动前会清理无进程占用的 IsRunning 锁，并隔离不完整的 FreeSurfer subject，避免续跑坏缓存。",
        },
    )
    return status


def reusable_fmriprep_outputs(ctx: RunContext) -> dict:
    base = ctx.output_subject / "fmriprep" / "output" / ctx.subject
    sessions = sorted(selected_session_names(ctx.input_subject))
    recon_backend = surface_recon_backend()
    recon_subject_dir = find_recon_subject_dir(ctx, recon_backend)
    fs_subjects_dir, fs_reuse = usable_fs_subjects_dir(ctx, recon_backend)
    status = {
        "complete": False,
        "sessions": {},
        "missing": [],
        "surface_recon_backend": recon_backend,
        "fs_subjects_dir": fs_subjects_dir,
        "fs_reuse": fs_reuse,
        "recon_subject_dir": str(recon_subject_dir) if recon_subject_dir else "",
    }
    if not sessions:
        status["missing"].append("未发现输入 session")
        return status
    for session in sessions:
        func_dir = base / session / "func"
        confounds = sorted(func_dir.glob("*desc-confounds_timeseries.tsv"))
        preproc = sorted(func_dir.glob("*space-T1w_desc-preproc_bold.nii.gz"))
        surfaces = sorted(func_dir.glob("*_space-*_bold.func.gii"))
        ok = bool(confounds and preproc)
        status["sessions"][session] = {
            "complete": ok,
            "confounds": [str(p) for p in confounds],
            "preproc_bold": [str(p) for p in preproc],
            "surface_bold": [str(p) for p in surfaces],
            "surface_recon_subject_dir": str(recon_subject_dir) if recon_subject_dir else "",
        }
        if not ok:
            status["missing"].append(session)
    status["complete"] = not status["missing"]
    return status


def locate_fmriprep_outputs(ctx: RunContext) -> dict:
    base = ctx.output_subject / "fmriprep" / "output"
    candidates = sorted(base.rglob("*desc-preproc_bold.nii.gz"))
    confounds = sorted(base.rglob("*desc-confounds_timeseries.tsv"))
    surfaces = sorted(base.rglob("*space-*_bold.func.gii"))
    anat = sorted(base.rglob("*desc-preproc_T1w.nii.gz"))
    found = {
        "base": str(base),
        "preproc_bold": str(candidates[0]) if candidates else "",
        "confounds": str(confounds[0]) if confounds else "",
        "surface_bold": [str(p) for p in surfaces],
        "preproc_t1w": [str(p) for p in anat],
    }
    write_json(ctx.output_subject / "fmriprep" / "config" / "located_outputs.json", found)
    return found


def locate_fmriprep_bold_runs(ctx: RunContext) -> list[dict[str, str]]:
    base = ctx.output_subject / "fmriprep" / "output"
    allowed_sessions = selected_session_names(ctx.input_subject)
    runs = []
    for confounds in sorted(base.rglob("*desc-confounds_timeseries.tsv")):
        prefix = confounds.name.removesuffix("_desc-confounds_timeseries.tsv")
        session = session_from_bold_base(prefix)
        if allowed_sessions and session not in allowed_sessions:
            continue
        func_dir = confounds.parent
        t1w_matches = sorted(func_dir.glob(f"{prefix}_space-T1w_desc-preproc_bold.nii.gz"))
        if not t1w_matches:
            t1w_matches = sorted(func_dir.glob(f"{prefix}*space-T1w_desc-preproc_bold.nii.gz"))
        if not t1w_matches:
            continue
        surfaces = sorted(func_dir.glob(f"{prefix}_hemi-*_space-*_bold.func.gii"))
        runs.append(
            {
                "confounds": str(confounds),
                "preproc_bold": str(t1w_matches[0]),
                "surface_bold": [str(path) for path in surfaces],
            }
        )
    write_json(ctx.output_subject / "fmriprep" / "config" / "located_bold_runs.json", runs)
    return runs


def copy_selected_fmriprep_figures(ctx: RunContext) -> list[Path]:
    base = ctx.output_subject / "fmriprep" / "output" / ctx.subject / "figures"
    allowed_sessions = selected_session_names(ctx.input_subject)
    copied: list[Path] = []
    if not base.exists():
        for session in sorted(allowed_sessions):
            write_text(ctx.output_subject / session / "figures" / "STATUS.txt", f"未找到 fMRIPrep figures 目录：{base}")
        return copied
    for src in sorted(base.iterdir()):
        if not src.is_file():
            continue
        matched_sessions = [session for session in sorted(allowed_sessions) if f"_{session}_" in src.name]
        if allowed_sessions and not matched_sessions:
            continue
        for session in matched_sessions:
            out_dir = ctx.output_subject / session / "figures"
            out_dir.mkdir(parents=True, exist_ok=True)
            dst = out_dir / src.name
            shutil.copyfile(src, dst)
            copied.append(dst)
    for session in sorted(allowed_sessions):
        count = sum(1 for p in copied if f"/{session}/figures/" in str(p))
        write_text(ctx.output_subject / session / "figures" / "STATUS.txt", f"已复制 {session} 的 fMRIPrep figures {count} 个。")
    return copied


def prune_unselected_fmriprep_session_dirs(ctx: RunContext) -> None:
    if os.environ.get("FMRI_PRUNE_UNSELECTED_SESSIONS", "0") != "1":
        return
    allowed_sessions = selected_session_names(ctx.input_subject)
    if not allowed_sessions:
        return
    subject_dir = ctx.output_subject / "fmriprep" / "output" / ctx.subject
    if not subject_dir.exists():
        return
    removed = []
    for path in sorted(subject_dir.iterdir()):
        if path.is_dir() and path.name.startswith("ses-") and path.name not in allowed_sessions:
            shutil.rmtree(path)
            removed.append(path.name)
    if removed:
        write_text(ctx.output_subject / "fmriprep" / "config" / "pruned_sessions.txt", "已移除未选择 session 目录：\n" + "\n".join(removed))


def standard_bold_base(preproc_bold: Path) -> str:
    name = preproc_bold.name.removesuffix(".nii.gz").removesuffix(".nii")
    marker = "_space-T1w_desc-preproc_bold"
    if marker in name:
        name = name.split(marker, 1)[0] + marker
    else:
        name = name + marker
    return re.sub(r"_run-\d+", "", name)


def qc_bold_base(base: str) -> str:
    return re.sub(r"_space-[^_]+_desc-preproc_bold$", "", base)


def session_from_bold_base(base: str) -> str:
    match = re.search(r"_ses-([^_]+)", base)
    return f"ses-{match.group(1)}" if match else "ses-unknown"


def _column_or_zero(df: pd.DataFrame, name: str, length: int) -> np.ndarray:
    if name in df:
        return pd.to_numeric(df[name], errors="coerce").fillna(0.0).to_numpy(dtype=np.float32)
    return np.zeros(length, dtype=np.float32)


def save_text_vector(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for value in values:
            f.write(f"{float(value):.10g}\n")


def build_regressors_from_fmriprep(ctx: RunContext, confounds_tsv: Path, preproc_bold: Path | None = None) -> tuple[Path, Path, np.ndarray, float]:
    df = pd.read_csv(confounds_tsv, sep="\t")
    df = df.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    t = len(df)
    base = standard_bold_base(preproc_bold) if preproc_bold else "sub-YZ1_ses-mri0_task-sleep0_space-T1w_desc-preproc_bold"
    session = session_from_bold_base(base)

    motion_names = ["trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"]
    motion = np.column_stack([_column_or_zero(df, c, t) for c in motion_names])
    motion_deriv = np.vstack([np.zeros((1, motion.shape[1]), dtype=np.float32), np.diff(motion, axis=0)])
    rp12 = np.column_stack([motion, motion_deriv]).astype(np.float32)

    compcor_cols = [c for c in df.columns if "comp_cor" in c][:50]
    pca50 = df[compcor_cols].to_numpy(dtype=np.float32) if compcor_cols else np.zeros((t, 0), dtype=np.float32)
    csf_wm_cols = [c for c in ["csf", "white_matter"] if c in df.columns]
    csf_wm = df[csf_wm_cols].to_numpy(dtype=np.float32) if csf_wm_cols else np.zeros((t, 0), dtype=np.float32)

    out = ctx.output_subject / session / "clean_data_regressor" / "volume"
    combo = out / "combination"
    combo.mkdir(parents=True, exist_ok=True)
    rp_cols = motion_names + [f"{c}_derivative1" for c in motion_names]
    savemat(out / f"{base}_12rp.mat", {"score": rp12, "columns": np.array(rp_cols, dtype=object)})
    savemat(out / f"{base}_50pca.mat", {"score": pca50, "columns": np.array(compcor_cols, dtype=object)})
    savemat(out / f"{base}_csf_wm.mat", {"score": csf_wm, "columns": np.array(csf_wm_cols, dtype=object)})

    reg_12_50 = np.column_stack([np.ones(t, dtype=np.float32), rp12, pca50]).astype(np.float32)
    reg_50_csf = np.column_stack([np.ones(t, dtype=np.float32), pca50, csf_wm]).astype(np.float32)
    reg = np.column_stack([np.ones(t, dtype=np.float32), rp12, pca50, csf_wm]).astype(np.float32)
    reg_cols = ["constant"] + [f"rp12_{i + 1:02d}" for i in range(rp12.shape[1])] + compcor_cols + csf_wm_cols
    savemat(combo / f"{base}_12rp_50pca.mat", {"score": reg_12_50})
    savemat(combo / f"{base}_50pca_csf_wm.mat", {"score": reg_50_csf})
    savemat(combo / f"{base}_12rp_50pca_csf_wm.mat", {"score": reg, "columns": np.array(reg_cols, dtype=object)})

    reg_csv = combo / f"{base}_12rp_50pca_csf_wm.csv"
    with reg_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(reg_cols)
        writer.writerows(reg.tolist())

    conf_copy = ctx.output_subject / session / "clean_data_regressor" / "volume" / confounds_tsv.name
    conf_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(confounds_tsv, conf_copy)
    source_json = confounds_tsv.with_suffix(".json")
    if source_json.exists():
        shutil.copyfile(source_json, conf_copy.with_suffix(".json"))
    write_text(ctx.output_subject / session / "clean_data_regressor" / "DESCRIPTION.txt", "本目录保存从 fMRIPrep desc-confounds_timeseries.tsv 提取的 12rp、50pca、csf_wm 及其组合回归器。")
    return conf_copy, reg_csv, reg, 2.0


def load_bold(path: Path) -> tuple[nib.Nifti1Image, np.ndarray]:
    img = nib.load(str(path))
    data = np.asanyarray(img.dataobj).astype(np.float32)
    if data.ndim != 4:
        raise ValueError(f"BOLD 不是 4D：{path}")
    return img, data


def get_tr(bold_json: Path | None) -> float:
    if bold_json and bold_json.exists():
        try:
            meta = json.loads(bold_json.read_text(encoding="utf-8"))
            return float(meta.get("RepetitionTime") or meta.get("TR") or 2.0)
        except Exception:
            return 2.0
    return 2.0


def build_confounds_and_regressors(ctx: RunContext, bold_path: Path) -> tuple[Path, Path, np.ndarray, np.ndarray, float]:
    img, data = load_bold(bold_path)
    tr = get_tr(bold_path.with_suffix("").with_suffix(".json"))
    t = data.shape[-1]
    flat = data.reshape(-1, t)
    mask = np.nanmean(flat, axis=1) > 0
    sampled = flat[mask]
    mean_signal = np.nanmean(sampled, axis=0)
    mean_signal = np.nan_to_num(mean_signal)
    mean_centered = mean_signal - mean_signal.mean()
    derivative = np.r_[0, np.diff(mean_centered)]
    trend = np.linspace(-1, 1, t)
    quad = trend**2
    confounds = np.column_stack([mean_signal, mean_centered, derivative, trend, quad])

    base = standard_bold_base(bold_path)
    session = session_from_bold_base(base)
    conf_path = ctx.output_subject / session / "clean_data_regressor" / "volume" / f"{base}_basic_confounds_from_bold.csv"
    with conf_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["global_signal", "global_signal_centered", "global_derivative", "linear_trend", "quadratic_trend"])
        writer.writerows(confounds.tolist())

    reg = np.column_stack([np.ones(t), mean_centered, derivative, trend, quad])
    reg_path = ctx.output_subject / session / "clean_data_regressor" / "volume" / f"{base}_basic_nuisance_regressors.csv"
    with reg_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["constant", "global_signal_centered", "global_derivative", "linear_trend", "quadratic_trend"])
        writer.writerows(reg.tolist())

    write_text(
        ctx.output_subject / session / "clean_data_regressor" / "fmriprep_regressor_STATUS.txt",
        "是否必须先经过 fMRIPrep：标准流程必须。motion/csf/wm/CompCor/PCA 回归器依赖 fMRIPrep 生成的 desc-confounds_timeseries.tsv/json、脑掩膜和组织分割。当前 fMRIPrep 未完整完成时，使用从原始 BOLD 生成的 basic_nuisance_regressors.csv 仅测试去噪工作流，不等价于正式 fMRIPrep 后处理。",
    )
    return conf_path, reg_path, reg.astype(np.float32), mask, tr


def denoise_bold(ctx: RunContext, bold_path: Path, regressors: np.ndarray, mask: np.ndarray, output_path: Path | None = None) -> Path:
    img, data = load_bold(bold_path)
    shape = data.shape
    t = shape[-1]
    y = data.reshape(-1, t)
    x = regressors
    x = x - x.mean(axis=0, keepdims=True)
    x[:, 0] = 1.0
    pinv = np.linalg.pinv(x).astype(np.float32)
    cleaned = np.zeros_like(y, dtype=np.float32)
    chunk = 20000
    for start in range(0, y.shape[0], chunk):
        end = min(start + chunk, y.shape[0])
        yy = y[start:end].T.astype(np.float32)
        beta = pinv @ yy
        fitted = x @ beta
        resid = yy - fitted + yy.mean(axis=0, keepdims=True)
        cleaned[start:end] = resid.T
    cleaned_img = nib.Nifti1Image(cleaned.reshape(shape), img.affine, img.header)
    out = output_path or ctx.output_subject / "clean_data" / "volume" / bold_path.name.replace("_bold.nii.gz", "_desc-12rp50pcaCsfWmDenoised_bold.nii.gz")
    out.parent.mkdir(parents=True, exist_ok=True)
    nib.save(cleaned_img, str(out))
    session = session_from_bold_base(standard_bold_base(out))
    info = {
        "method": "OLS nuisance regression",
        "regressor_file": str(ctx.output_subject / session / "clean_data_regressor" / "volume" / "combination"),
        "note": "基础测试去噪结果；标准 nuisance regression 需要 fMRIPrep confounds。",
    }
    write_json(ctx.output_subject / session / "clean_info" / "volume" / f"{out.name.removesuffix('.nii.gz')}_denoise_info.json", info)
    return out


def denoise_surfaces(ctx: RunContext, surface_files: list[Path], regressors: np.ndarray) -> list[Path]:
    outputs = []
    if not surface_files:
        for session in sorted(selected_session_names(ctx.input_subject)):
            write_text(ctx.output_subject / session / "surface_transform" / "STATUS.txt", "未找到 fMRIPrep surface BOLD GIFTI 输出，surface 去噪未运行。若需要 fsnative/fsaverage surface，请允许 fMRIPrep/FreeSurfer 生成 surface 文件。")
        return outputs
    x = regressors.astype(np.float32)
    x = x - x.mean(axis=0, keepdims=True)
    x[:, 0] = 1.0
    pinv = np.linalg.pinv(x).astype(np.float32)
    for src in surface_files:
        gii = nib.load(str(src))
        if not hasattr(gii, "darrays") or not gii.darrays:
            continue
        data = np.vstack([arr.data.astype(np.float32) for arr in gii.darrays])
        if data.shape[0] != x.shape[0]:
            session = session_from_bold_base(src.name)
            write_text(ctx.output_subject / session / "clean_data" / "surface" / f"{src.name}.STATUS.txt", f"surface 时间点 {data.shape[0]} 与回归器时间点 {x.shape[0]} 不一致，跳过。")
            continue
        beta = pinv @ data
        resid = data - x @ beta + data.mean(axis=0, keepdims=True)
        out_gii = nib.gifti.GiftiImage(meta=gii.meta)
        for idx, arr in enumerate(gii.darrays):
            new_arr = nib.gifti.GiftiDataArray(resid[idx].astype(np.float32), intent=arr.intent, datatype="NIFTI_TYPE_FLOAT32", meta=arr.meta)
            out_gii.add_gifti_data_array(new_arr)
        session = session_from_bold_base(src.name)
        space_match = re.search(r"_space-([^_]+)_bold\.func\.gii$", src.name)
        hemi_match = re.search(r"_hemi-([LR])_", src.name)
        task_match = re.search(r"_task-([^_]+)", src.name)
        space = space_match.group(1) if space_match else "unknown"
        hemi = {"L": "lh", "R": "rh"}.get(hemi_match.group(1), "hemi") if hemi_match else "hemi"
        task = task_match.group(1) if task_match else "task"
        out_name = f"{ctx.subject}_{session}_task-{task}_space-{space}_{hemi}_12rp_50pca_csf_wm.gii"
        out = ctx.output_subject / session / "clean_data" / "surface" / out_name
        out.parent.mkdir(parents=True, exist_ok=True)
        nib.save(out_gii, str(out))
        valid = np.isfinite(resid).all(axis=0) & (np.nanstd(resid, axis=0) > 0)
        mask_csv = out.with_name(out.stem + "_mask.csv")
        save_text_vector(mask_csv, valid.astype(float))
        outputs.append(out)
    return outputs


def _surface_project_subject(ctx: RunContext) -> tuple[Path, Path] | None:
    backend = surface_recon_backend()
    subject_dir = find_recon_subject_dir(ctx, backend)
    if not subject_dir:
        return None
    surf_dir = subject_dir / "surf"
    required = [surf_dir / "lh.white", surf_dir / "rh.white", surf_dir / "lh.pial", surf_dir / "rh.pial"]
    if not all(path.exists() and path.stat().st_size > 0 for path in required):
        return None
    return subject_dir.parent, subject_dir


def _mgh_to_func_gii(mgh_path: Path, out_gii: Path) -> None:
    data = np.asarray(nib.load(str(mgh_path)).get_fdata(), dtype=np.float32).squeeze()
    if data.ndim == 1:
        data = data[:, np.newaxis]
    if data.shape[0] < data.shape[-1]:
        data = data.T
    out_gii.parent.mkdir(parents=True, exist_ok=True)
    gii = nib.gifti.GiftiImage()
    for frame in range(data.shape[1]):
        gii.add_gifti_data_array(
            nib.gifti.GiftiDataArray(
                data[:, frame].astype(np.float32),
                intent="NIFTI_INTENT_TIME_SERIES",
                datatype="NIFTI_TYPE_FLOAT32",
            )
        )
    nib.save(gii, str(out_gii))


def project_clean_bold_to_fsnative_surfaces(ctx: RunContext, clean_bold: Path, base: str) -> tuple[list[Path], list[Path]]:
    subject_info = _surface_project_subject(ctx)
    session = session_from_bold_base(base)
    if subject_info is None:
        write_text(
            ctx.output_subject / session / "surface_transform" / "STATUS.txt",
            "未找到可用于投影的完整 FastSurfer/FreeSurfer surface subject，无法生成 fsnative clean surface。",
        )
        return [], []
    subjects_dir, subject_dir = subject_info
    if not shutil.which("mri_vol2surf"):
        write_text(ctx.output_subject / session / "surface_transform" / "STATUS.txt", "未找到 mri_vol2surf，无法生成 fsnative clean surface。")
        return [], []
    clean_surfaces: list[Path] = []
    transform_sources: list[Path] = []
    task_match = re.search(r"_task-([^_]+)", base)
    task = task_match.group(1) if task_match else "task"
    env = os.environ.copy()
    env["SUBJECTS_DIR"] = str(subjects_dir)
    for hemi, bids_hemi in (("lh", "L"), ("rh", "R")):
        generated_dir = ctx.output_subject / session / "surface_transform" / "generated"
        mgh_path = generated_dir / f"{qc_bold_base(base)}_hemi-{bids_hemi}_space-fsnative_bold.mgh"
        source_gii = generated_dir / f"{qc_bold_base(base)}_hemi-{bids_hemi}_space-fsnative_bold.func.gii"
        cmd = [
            "mri_vol2surf",
            "--src",
            str(clean_bold),
            "--out",
            str(mgh_path),
            "--out_type",
            "mgh",
            "--regheader",
            subject_dir.name,
            "--hemi",
            hemi,
            "--surf",
            "white",
            "--projfrac-avg",
            "0",
            "1",
            "0.2",
        ]
        generated_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(cmd, text=True, capture_output=True, env=env, check=False)
        if proc.returncode != 0:
            write_text(
                ctx.output_subject / session / "surface_transform" / f"{hemi}_mri_vol2surf_STATUS.txt",
                "COMMAND:\n" + " ".join(cmd) + "\n\nSTDOUT:\n" + proc.stdout + "\n\nSTDERR:\n" + proc.stderr,
            )
            continue
        _mgh_to_func_gii(mgh_path, source_gii)
        clean_gii = ctx.output_subject / session / "clean_data" / "surface" / f"{ctx.subject}_{session}_task-{task}_space-fsnative_{hemi}_12rp_50pca_csf_wm.gii"
        clean_gii.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_gii, clean_gii)
        clean_surfaces.append(clean_gii)
        transform_sources.append(source_gii)
    if transform_sources:
        write_json(
            ctx.output_subject / session / "surface_transform" / "surface_projection.json",
            {
                "method": "mri_vol2surf --regheader projection from denoised T1w clean BOLD to fsnative surface",
                "source_clean_bold": str(clean_bold),
                "subjects_dir": str(subjects_dir),
                "subject_dir": str(subject_dir),
                "regheader_subject": subject_dir.name,
                "generated_surface_bold": [str(path) for path in transform_sources],
                "clean_surface": [str(path) for path in clean_surfaces],
            },
        )
    return clean_surfaces, transform_sources


def fallback_surface_transform_sources(ctx: RunContext) -> list[Path]:
    return sorted((ctx.output_subject).glob("ses-*/surface_transform/generated/*_bold.func.gii"))


def organize_surface_transform(ctx: RunContext, surface_files: list[Path]) -> list[Path]:
    outputs: list[Path] = []
    manifests: dict[str, list[dict[str, object]]] = {}
    mode = os.environ.get("FMRI_SURFACE_TRANSFORM_MODE", "reference").strip().lower()
    if mode not in {"hardlink", "copy", "reference"}:
        mode = "reference"
    if not surface_files:
        for session in sorted(selected_session_names(ctx.input_subject)):
            out_dir = ctx.output_subject / session / "surface_transform"
            write_text(
                out_dir / "STATUS.txt",
                "未找到 fMRIPrep surface BOLD GIFTI 输出。完整 surface_transform 需要 fMRIPrep 输出 *_space-fsnative_bold.func.gii 或 *_space-fsaverage_bold.func.gii。",
            )
            write_json(out_dir / "manifest.json", {"storage_mode": mode, "surface_files": []})
        return outputs
    for src in surface_files:
        session = session_from_bold_base(src.name)
        out_dir = ctx.output_subject / session / "surface_transform"
        out_dir.mkdir(parents=True, exist_ok=True)
        manifests.setdefault(session, [])
        if mode == "reference":
            for stale in out_dir.glob("*_bold.func.gii"):
                stale.unlink()
        dst = out_dir / src.name
        stored_surface = ""
        storage_method = "reference"
        if mode != "reference":
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            if mode == "hardlink":
                try:
                    os.link(src, dst)
                    storage_method = "hardlink"
                except OSError:
                    shutil.copyfile(src, dst)
                    storage_method = "copy-fallback"
            else:
                shutil.copyfile(src, dst)
                storage_method = "copy"
            stored_surface = str(dst)
            outputs.append(dst)
        mask_path = out_dir / src.name.replace("_bold.func.gii", "_desc-validVertices_mask.npy")
        vertex_count = 0
        timepoints = 0
        try:
            gii = nib.load(str(src))
            data = np.vstack([arr.data.astype(np.float32) for arr in gii.darrays])
            timepoints = int(data.shape[0])
            vertex_count = int(data.shape[1]) if data.ndim == 2 else 0
            valid = np.isfinite(data).all(axis=0) & (np.nanstd(data, axis=0) > 0)
            np.save(mask_path, valid.astype(bool))
            outputs.append(mask_path)
        except Exception as exc:
            write_text(out_dir / f"{src.name}.STATUS.txt", f"surface mask 生成失败: {type(exc).__name__}: {exc}")
        manifests[session].append(
            {
                "source": str(src),
                "surface": stored_surface,
                "storage_method": storage_method,
                "valid_vertex_mask": str(mask_path) if mask_path.exists() else "",
                "timepoints": timepoints,
                "vertices": vertex_count,
            }
        )
    for session, manifest in manifests.items():
        out_dir = ctx.output_subject / session / "surface_transform"
        write_json(out_dir / "manifest.json", {"storage_mode": mode, "surface_files": manifest})
        source_label = "fallback 生成的 fsnative surface BOLD GIFTI" if any("/surface_transform/generated/" in item["source"] for item in manifest) else "fMRIPrep surface BOLD GIFTI"
        write_text(out_dir / "STATUS.txt", f"已整理 {session} 的 {source_label} {len(manifest)} 个，storage_mode={mode}，并为可读取文件生成有效顶点 mask。")
    return outputs


def compute_outliers(ctx: RunContext, clean_bold: Path, confounds_tsv: Path | None = None, base: str | None = None) -> tuple[Path, Path]:
    _, data = load_bold(clean_bold)
    flat = data.reshape(-1, data.shape[-1])
    mask = np.nanmean(flat, axis=1) > 0
    sampled = flat[mask]
    diff = np.diff(sampled, axis=1)
    dvars = np.r_[0, np.sqrt(np.nanmean(diff * diff, axis=0))]
    global_signal = np.nanmean(sampled, axis=0)
    fd_like = np.r_[0, np.abs(np.diff(global_signal))]
    if confounds_tsv is not None and confounds_tsv.exists():
        df = pd.read_csv(confounds_tsv, sep="\t").replace([np.inf, -np.inf], np.nan).fillna(0.0)
        if "framewise_displacement" in df:
            fd_like = pd.to_numeric(df["framewise_displacement"], errors="coerce").fillna(0.0).to_numpy(dtype=np.float32)
        dvars_col = "std_dvars" if "std_dvars" in df else "dvars" if "dvars" in df else None
        if dvars_col:
            dvars = pd.to_numeric(df[dvars_col], errors="coerce").fillna(0.0).to_numpy(dtype=np.float32)
    fd_thr = float(np.nanmean(fd_like) + 2 * np.nanstd(fd_like))
    dvars_thr = float(np.nanmean(dvars) + 2 * np.nanstd(dvars))
    bad = ((fd_like > fd_thr) | (dvars > dvars_thr)).astype(int)

    if base:
        session = session_from_bold_base(base)
        stat_dir = ctx.output_subject / session / "clean_data_regressor_stat" / "volume"
        save_text_vector(stat_dir / f"{base}_12rp_50pca_csf_wm_fd_value", fd_like)
        save_text_vector(stat_dir / f"{base}_12rp_50pca_csf_wm_dvars_value", dvars)
        save_text_vector(stat_dir / f"{base}_12rp_50pca_csf_wm_fd_confound", (fd_like > 0.2).astype(float))
        p75 = float(np.nanquantile(dvars, 0.75))
        p25 = float(np.nanquantile(dvars, 0.25))
        dvars_iqr_thr = p75 + 1.5 * (p75 - p25)
        save_text_vector(stat_dir / f"{base}_12rp_50pca_csf_wm_dvars_confound", (dvars > dvars_iqr_thr).astype(float))
        stat_csv = stat_dir / f"{base}_fd_dvars_summary.csv"
    else:
        stat_csv = ctx.output_subject / "clean_data_regressor_stat" / "fd_dvars_basic.csv"
    with stat_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["volume", "fd_like", "dvars", "bad_epoch"])
        for i, row in enumerate(zip(fd_like, dvars, bad)):
            writer.writerow([i, float(row[0]), float(row[1]), int(row[2])])
    info_json = (ctx.output_subject / session_from_bold_base(base) / "clean_info" / "volume" / f"{base}_fd_dvars_info.json") if base else ctx.output_subject / "clean_data" / "info" / "bad_epochs.json"
    write_json(info_json, {"fd_like_threshold": fd_thr, "dvars_threshold": dvars_thr, "bad_epochs": bad.tolist()})
    return stat_csv, info_json


def _zscore(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    std = float(np.nanstd(values))
    if std == 0.0 or not np.isfinite(std):
        return values * 0.0
    return (values - float(np.nanmean(values))) / std


def _confound_series(confounds_tsv: Path | None, name: str, length: int) -> np.ndarray:
    if confounds_tsv is None or not confounds_tsv.exists():
        return np.zeros(length, dtype=np.float32)
    try:
        df = pd.read_csv(confounds_tsv, sep="\t")
    except Exception:
        return np.zeros(length, dtype=np.float32)
    aliases = {
        "GSCSF": ["csf", "csf_derivative1", "csf_derivative"],
        "GSWM": ["white_matter", "wm", "white_matter_derivative1"],
        "DVARS": ["std_dvars", "dvars"],
        "FD": ["framewise_displacement"],
    }
    for col in aliases.get(name, [name]):
        if col in df:
            values = pd.to_numeric(df[col], errors="coerce").fillna(0.0).to_numpy(dtype=np.float32)
            if len(values) == length:
                return values
            if len(values) > length:
                return values[:length]
            return np.pad(values, (0, length - len(values)), constant_values=0.0)
    return np.zeros(length, dtype=np.float32)


def _series_stats(values: np.ndarray) -> dict[str, float]:
    values = np.nan_to_num(np.asarray(values, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    return {
        "max": float(np.nanmax(values)) if values.size else 0.0,
        "mean": float(np.nanmean(values)) if values.size else 0.0,
        "sigma": float(np.nanstd(values)) if values.size else 0.0,
    }


def _stats_delta(pre: np.ndarray, post: np.ndarray) -> dict[str, float]:
    pre_stats = _series_stats(pre)
    post_stats = _series_stats(post)
    pre_sigma = pre_stats["sigma"]
    return {
        "pre_mean": pre_stats["mean"],
        "post_mean": post_stats["mean"],
        "mean_delta": post_stats["mean"] - pre_stats["mean"],
        "pre_sigma": pre_sigma,
        "post_sigma": post_stats["sigma"],
        "sigma_delta": post_stats["sigma"] - pre_sigma,
        "sigma_reduction_percent": (1.0 - post_stats["sigma"] / pre_sigma) * 100.0 if pre_sigma > 0 else 0.0,
        "pre_max": pre_stats["max"],
        "post_max": post_stats["max"],
    }


def _dvars_from_carpet_data(carpet_data: np.ndarray) -> np.ndarray:
    if carpet_data.ndim != 2 or carpet_data.shape[1] == 0:
        return np.zeros(0, dtype=np.float32)
    if carpet_data.shape[1] == 1:
        return np.zeros(1, dtype=np.float32)
    diff = np.diff(np.nan_to_num(carpet_data.astype(np.float32), nan=0.0), axis=1)
    dvars = np.sqrt(np.nanmean(diff * diff, axis=0)).astype(np.float32)
    return np.r_[np.float32(0.0), dvars]


def _find_preproc_bold_for_base(ctx: RunContext, base: str) -> Path | None:
    for run in locate_fmriprep_bold_runs(ctx):
        candidate = Path(run["preproc_bold"])
        if standard_bold_base(candidate) == base:
            return candidate
    return None


def _common_valid_carpet_data(pre_data: np.ndarray, post_data: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if pre_data.shape != post_data.shape or pre_data.ndim != 4:
        raise ValueError(f"pre/post BOLD shape mismatch: {pre_data.shape} vs {post_data.shape}")
    n_tp = pre_data.shape[-1]
    pre_flat = pre_data.reshape(-1, n_tp)
    post_flat = post_data.reshape(-1, n_tp)
    finite = np.all(np.isfinite(pre_flat), axis=1) & np.all(np.isfinite(post_flat), axis=1)
    active = (np.nanstd(pre_flat, axis=1) > 0) & (np.nanstd(post_flat, axis=1) > 0)
    mask = finite & active
    if not np.any(mask):
        raise ValueError("no shared valid brain-mask voxels for pre/post carpetplot comparison")
    return pre_flat[mask].astype(np.float32), post_flat[mask].astype(np.float32), mask


CSF_ASEG_LABELS = {4, 5, 14, 15, 24, 31, 43, 44, 63}
WM_ASEG_LABELS = {2, 7, 41, 46, 77, 78, 79, 80, 81, 82, 251, 252, 253, 254, 255}


def _candidate_segmentation_paths(ctx: RunContext, session: str) -> list[Path]:
    fmriprep_subject = ctx.output_subject / "fmriprep" / "output" / ctx.subject
    candidates: list[Path] = []
    candidates.extend(sorted((fmriprep_subject / session / "func").glob("*desc-aseg_dseg.nii.gz")))
    candidates.extend(sorted((fmriprep_subject / session / "func").glob("*desc-aparcaseg_dseg.nii.gz")))
    candidates.extend(sorted((fmriprep_subject / session / "anat").glob("*desc-aseg_dseg.nii.gz")))
    candidates.extend(sorted((fmriprep_subject / session / "anat").glob("*desc-aparcaseg_dseg.nii.gz")))
    candidates.extend(sorted((fmriprep_subject / "anat").glob("*desc-aseg_dseg.nii.gz")))
    candidates.extend(sorted((fmriprep_subject / "anat").glob("*desc-aparcaseg_dseg.nii.gz")))
    for backend in ("fastsurfer", "freesurfer"):
        subject_dir = find_recon_subject_dir(ctx, backend)
        if subject_dir:
            mri_dir = subject_dir / "mri"
            for name in ("aseg.mgz", "aseg.auto.mgz", "aparc.DKTatlas+aseg.deep.mgz", "aparc+aseg.mgz"):
                candidates.append(mri_dir / name)
    seen: set[Path] = set()
    unique = []
    for path in candidates:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _segmentation_on_bold_grid(seg_path: Path, bold_img: nib.Nifti1Image) -> np.ndarray | None:
    try:
        seg_img = nib.load(str(seg_path))
        if seg_img.shape[:3] != bold_img.shape[:3] or not np.allclose(seg_img.affine, bold_img.affine, atol=1e-3):
            from nibabel.processing import resample_from_to

            seg_img = resample_from_to(seg_img, (bold_img.shape[:3], bold_img.affine), order=0)
        return np.rint(np.asarray(seg_img.dataobj, dtype=np.float32)).astype(np.int32)
    except Exception:
        return None


def _mean_signal_for_labels(data: np.ndarray, seg: np.ndarray, labels: set[int]) -> np.ndarray | None:
    mask = np.isin(seg, list(labels))
    if not np.any(mask):
        return None
    values = data[mask, :]
    if values.size == 0:
        return None
    return np.nanmean(values, axis=0).astype(np.float32)


def tissue_signals_for_bold(ctx: RunContext, bold_img: nib.Nifti1Image, data: np.ndarray, base: str) -> tuple[dict[str, np.ndarray | None], dict[str, str]]:
    session = session_from_bold_base(base)
    n_tp = data.shape[-1]
    flat_data = data.reshape(-1, n_tp)
    signals: dict[str, np.ndarray | None] = {"CSF": None, "WM": None}
    sources = {
        "CSF": "",
        "WM": "",
    }
    for seg_path in _candidate_segmentation_paths(ctx, session):
        seg = _segmentation_on_bold_grid(seg_path, bold_img)
        if seg is None:
            continue
        if signals["CSF"] is None:
            csf = _mean_signal_for_labels(flat_data, seg.reshape(-1), CSF_ASEG_LABELS)
            if csf is not None:
                signals["CSF"] = csf
                sources["CSF"] = f"mean over CSF aseg labels from {seg_path}"
        if signals["WM"] is None:
            wm = _mean_signal_for_labels(flat_data, seg.reshape(-1), WM_ASEG_LABELS)
            if wm is not None:
                signals["WM"] = wm
                sources["WM"] = f"mean over WM aseg labels from {seg_path}"
        if signals["CSF"] is not None and signals["WM"] is not None:
            break
    return signals, sources


def clean_tissue_signals(ctx: RunContext, clean_bold: Path, base: str, data: np.ndarray, confounds_tsv: Path | None) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    bold_img = nib.load(str(clean_bold))
    n_tp = data.shape[-1]
    signals, sources = tissue_signals_for_bold(ctx, bold_img, data, base)
    clean_signals = {
        "CSF": signals["CSF"] if signals["CSF"] is not None else _confound_series(confounds_tsv, "GSCSF", n_tp),
        "WM": signals["WM"] if signals["WM"] is not None else _confound_series(confounds_tsv, "GSWM", n_tp),
    }
    clean_sources = {
        "CSF": f"clean BOLD {sources['CSF']}" if sources["CSF"] else "fallback: fMRIPrep confounds csf; no usable segmentation mask found",
        "WM": f"clean BOLD {sources['WM']}" if sources["WM"] else "fallback: fMRIPrep confounds white_matter; no usable segmentation mask found",
    }
    return clean_signals, clean_sources


def write_carpetplot_signal_comparison(
    ctx: RunContext,
    base: str,
    tr: float,
    confounds_tsv: Path | None,
    clean_confounds: dict[str, np.ndarray],
    clean_sources: dict[str, str],
    clean_carpet_data: np.ndarray,
    pre_carpet_data: np.ndarray | None = None,
    preproc_bold_path: Path | None = None,
    pre_tissue: dict[str, np.ndarray | None] | None = None,
    pre_tissue_sources: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    session = session_from_bold_base(base)
    out_base = ctx.output_subject / session / "qc_statistics" / f"{qc_bold_base(base)}_desc-carpetplotSignalComparison"
    n_tp = clean_carpet_data.shape[1] if clean_carpet_data.ndim == 2 else len(next(iter(clean_confounds.values()), []))
    if pre_carpet_data is None:
        pre_carpet_data = np.empty((0, n_tp), dtype=np.float32)
    preproc_bold = str(preproc_bold_path) if preproc_bold_path else ""
    if pre_tissue is None:
        pre_tissue = {"CSF": None, "WM": None}
    if pre_tissue_sources is None:
        pre_tissue_sources = {"CSF": "", "WM": ""}
    if not pre_carpet_data.size:
        try:
            candidate = _find_preproc_bold_for_base(ctx, base)
            if candidate is not None:
                preproc_bold = str(candidate)
                pre_img, pre_data = load_bold(candidate)
                pre_flat = pre_data.reshape(-1, pre_data.shape[-1])
                pre_mask = np.nanstd(pre_flat, axis=1) > 0
                pre_carpet_data = pre_flat[pre_mask]
                pre_tissue, pre_tissue_sources = tissue_signals_for_bold(ctx, pre_img, pre_data, base)
        except Exception:
            pre_carpet_data = np.empty((0, n_tp), dtype=np.float32)
    pre_gs = np.nanmean(pre_carpet_data, axis=0) if pre_carpet_data.size else _confound_series(confounds_tsv, "global_signal", n_tp)
    pre_dvars = _dvars_from_carpet_data(pre_carpet_data) if pre_carpet_data.size else _confound_series(confounds_tsv, "DVARS", n_tp)
    pre = {
        "GS": pre_gs,
        "CSF": pre_tissue["CSF"] if pre_tissue["CSF"] is not None else _confound_series(confounds_tsv, "GSCSF", n_tp),
        "WM": pre_tissue["WM"] if pre_tissue["WM"] is not None else _confound_series(confounds_tsv, "GSWM", n_tp),
        "DVARS": pre_dvars,
        "FD": _confound_series(confounds_tsv, "FD", n_tp),
    }
    post = {
        "GS": clean_confounds.get("GS", np.zeros(n_tp, dtype=np.float32)),
        "CSF": clean_confounds.get("GSCSF", pre["CSF"]),
        "WM": clean_confounds.get("GSWM", pre["WM"]),
        "DVARS": _dvars_from_carpet_data(clean_carpet_data),
        "FD": pre["FD"],
    }
    rows = [
        {
            "signal": "GS",
            "pre_source": "preproc BOLD brain-mask mean, recomputed",
            "post_source": "clean BOLD brain-mask mean, recomputed",
            "interpretation": "去噪后全脑共同波动应明显降低；过低或过高都需要结合 carpetplot 判断。",
            **_stats_delta(pre["GS"], post["GS"]),
        },
        {
            "signal": "CSF",
            "pre_source": f"preproc BOLD {pre_tissue_sources['CSF']}" if pre_tissue_sources["CSF"] else "fallback: fMRIPrep confounds csf; no usable segmentation mask found",
            "post_source": clean_sources.get("CSF", ""),
            "interpretation": "去噪后 CSF 残差信号应降低；若使用 fallback source，则说明当前输出缺少可用组织分割。",
            **_stats_delta(pre["CSF"], post["CSF"]),
        },
        {
            "signal": "WM",
            "pre_source": f"preproc BOLD {pre_tissue_sources['WM']}" if pre_tissue_sources["WM"] else "fallback: fMRIPrep confounds white_matter; no usable segmentation mask found",
            "post_source": clean_sources.get("WM", ""),
            "interpretation": "去噪后 WM 残差信号应降低；若使用 fallback source，则说明当前输出缺少可用组织分割。",
            **_stats_delta(pre["WM"], post["WM"]),
        },
        {
            "signal": "DVARS",
            "pre_source": "preproc BOLD voxelwise temporal difference RMS, recomputed",
            "post_source": "clean BOLD voxelwise temporal difference RMS, recomputed",
            "interpretation": "去噪后 DVARS 波动应下降；仍有尖峰时提示残余运动或突发伪影。",
            **_stats_delta(pre["DVARS"], post["DVARS"]),
        },
        {
            "signal": "FD",
            "pre_source": "fMRIPrep confounds framewise_displacement",
            "post_source": "same as pre; denoising does not change head motion estimates",
            "interpretation": "FD 是头动估计，不会因为信号回归而改变；用于解释 DVARS/GS 尖峰。",
            **_stats_delta(pre["FD"], post["FD"]),
        },
    ]
    csv_path = out_base.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["signal", "pre_source", "post_source", "pre_mean", "post_mean", "mean_delta", "pre_sigma", "post_sigma", "sigma_delta", "sigma_reduction_percent", "pre_max", "post_max", "interpretation"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    ts_path = out_base.with_name(out_base.name + "_timeseries.csv")
    with ts_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["frame", "time_seconds", "pre_GS", "post_GS", "pre_CSF", "post_CSF", "pre_WM", "post_WM", "pre_DVARS", "post_DVARS", "FD"])
        for frame in range(n_tp):
            writer.writerow(
                [
                    frame,
                    float(frame * tr if tr else frame),
                    float(pre["GS"][frame]),
                    float(post["GS"][frame]),
                    float(pre["CSF"][frame]),
                    float(post["CSF"][frame]),
                    float(pre["WM"][frame]),
                    float(post["WM"][frame]),
                    float(pre["DVARS"][frame]),
                    float(post["DVARS"][frame]),
                    float(pre["FD"][frame]),
                ]
            )
    json_path = out_base.with_suffix(".json")
    write_json(
        json_path,
        {
            "source_preproc_bold": preproc_bold,
            "source_confounds": str(confounds_tsv) if confounds_tsv else "",
            "summary_csv": str(csv_path),
            "timeseries_csv": str(ts_path),
            "signals": rows,
            "notes": [
                "pre/post GS 与 DVARS 优先从同一个共同有效 brain mask 上的 fMRIPrep preproc BOLD 和 clean BOLD 重算；缺少匹配 BOLD 时才回退。",
                "post CSF/WM 优先从 clean BOLD 和 aseg/FastSurfer segmentation mask 重算；缺少可用 mask 时才回退到 fMRIPrep confounds 并在 post_source 标注 fallback。",
                "FD 是头动参数，不能从 clean BOLD 重算；去噪前后应相同。",
            ],
        },
    )
    return csv_path, json_path


def _fmriprep_style_segments(n_voxels: int) -> dict[str, list[int]]:
    labels = ["Ctx GM", "dGM", "sWM+sCSF", "dWM+dCSF", "Cb", "Edge"]
    if n_voxels <= 0:
        return {labels[0]: []}
    weights = np.array([0.46, 0.08, 0.16, 0.12, 0.10, 0.08], dtype=np.float64)
    return _segments_from_weights(n_voxels, labels, weights)


def _segments_from_weights(n_voxels: int, labels: list[str], weights: np.ndarray) -> dict[str, list[int]]:
    if n_voxels <= 0:
        return {labels[0]: []}
    weights = np.asarray(weights, dtype=np.float64)
    weights = np.where(np.isfinite(weights) & (weights > 0), weights, 0.0)
    if not np.any(weights):
        weights = np.ones(len(labels), dtype=np.float64)
    cuts = np.rint(np.cumsum(weights / weights.sum()) * n_voxels).astype(int)
    cuts[-1] = n_voxels
    starts = np.r_[0, cuts[:-1]]
    segments: dict[str, list[int]] = {}
    for label, start, end in zip(labels, starts, cuts):
        if end > start:
            segments[label] = list(range(int(start), int(end)))
    return segments or {labels[0]: list(range(n_voxels))}


def _fmriprep_carpetplot_format(ctx: RunContext, base: str) -> tuple[list[str] | None, np.ndarray | None, dict[str, object], Path | None]:
    labels = ["Ctx GM", "dGM", "sWM+sCSF", "dWM+dCSF", "Cb", "Edge"]
    session = session_from_bold_base(base)
    figure_dir = ctx.output_subject / session / "figures"
    stem = qc_bold_base(base)
    candidates = sorted(figure_dir.glob(f"{stem}_run-*_desc-carpetplot_bold.svg"))
    if not candidates:
        candidates = sorted(figure_dir.glob("*desc-carpetplot_bold.svg"))
    if not candidates:
        return None, None, {}, None
    svg_path = candidates[0]
    try:
        svg = svg_path.read_text(encoding="utf-8", errors="ignore")
        viewbox_match = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', svg)
        layout: dict[str, object] = {}
        if viewbox_match:
            view_w = float(viewbox_match.group(1))
            view_h = float(viewbox_match.group(2))
            layout["figsize"] = (view_w / 72.0, view_h / 72.0)
        rects = [
            (float(x), float(y), float(w), float(h))
            for x, y, w, h in re.findall(r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"', svg)
            if float(w) > 100 and float(h) > 1
        ]
        if not rects:
            return None, None, layout, svg_path
        max_width = max(w for _, _, w, _ in rects)
        carpet_rects = [(x, y, w, h) for x, y, w, h in rects if abs(w - max_width) < 1e-3]
        confound_rects = [(x, y, w, h) for x, y, w, h in rects if abs(w - max_width) >= 1e-3]
        carpet_heights = [h for _, _, _, h in carpet_rects]
        if viewbox_match and carpet_rects:
            carpet_left = min(x for x, _, _, _ in carpet_rects)
            carpet_right = max(x + w for x, _, w, _ in carpet_rects)
            plot_top = min([y for _, y, _, _ in carpet_rects] + [y for _, y, _, _ in confound_rects])
            carpet_bottom = max(y + h for _, y, _, h in carpet_rects)
            carpet_top = min(y for _, y, _, _ in carpet_rects)
            confound_heights = [h for _, _, _, h in sorted(confound_rects, key=lambda item: item[1])[:5]]
            if len(confound_heights) < 5:
                confound_heights = [42.57792] * 5
            top_gaps = []
            ordered_top = sorted(confound_rects, key=lambda item: item[1])[:5] + [min(carpet_rects, key=lambda item: item[1])]
            for prev, cur in zip(ordered_top, ordered_top[1:]):
                top_gaps.append(max(0.0, cur[1] - (prev[1] + prev[3])))
            avg_axis = (sum(confound_heights) + (carpet_bottom - carpet_top)) / 6.0
            gap = float(np.median(top_gaps)) if top_gaps else 0.0
            layout.update(
                {
                    "left": carpet_left / view_w,
                    "right": carpet_right / view_w,
                    "top": 1.0 - plot_top / view_h,
                    "bottom": 1.0 - carpet_bottom / view_h,
                    "height_ratios": [*confound_heights, carpet_bottom - carpet_top],
                    "hspace": gap / avg_axis if avg_axis > 0 else 0.06,
                }
            )
        if len(carpet_heights) >= len(labels):
            weights = np.array(carpet_heights[: len(labels)], dtype=np.float64)
            return labels, weights, layout, svg_path
        return None, None, layout, svg_path
    except Exception:
        return None, None, {}, svg_path


def _percent_signal_change(pre_carpet: np.ndarray, post_carpet: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    baseline = np.nanmean(pre_carpet, axis=1, keepdims=True)
    baseline = np.where(np.abs(baseline) > 1e-6, baseline, 1.0)
    pre_psc = ((pre_carpet - baseline) / np.abs(baseline)) * 100.0
    post_psc = ((post_carpet - baseline) / np.abs(baseline)) * 100.0
    return pre_psc.astype(np.float32), post_psc.astype(np.float32)


def _write_prepost_carpetplot(
    out: Path,
    pre_carpet: np.ndarray,
    post_carpet: np.ndarray,
    segments: dict[str, list[int]],
    tr: float,
    title: str,
) -> Path:
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    from matplotlib.patches import Patch

    pre_psc, post_psc = _percent_signal_change(pre_carpet, post_carpet)
    combined = np.concatenate([pre_psc, post_psc], axis=1)
    vmin, vmax = np.nanpercentile(combined, [2, 98])
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
        vmin, vmax = -1.0, 1.0
    n_tp = pre_carpet.shape[1]
    xticks = np.linspace(0, n_tp - 1, endpoint=True, num=7)
    if tr:
        xticklabels = [f"{t // 60:02d}:{t % 60:02d}" for t in np.rint(tr * xticks).astype(int)]
    else:
        xticklabels = [str(int(t)) for t in np.rint(xticks).astype(int)]
    colors = list(plt.get_cmap("Paired").colors)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(18, 10), constrained_layout=False)
    grid = GridSpec(len(segments), 2, figure=fig, hspace=0.04, wspace=0.02, height_ratios=[max(1, len(v)) for v in segments.values()])
    for row, (label, indices) in enumerate(segments.items()):
        for col, data in enumerate((pre_psc, post_psc)):
            ax = fig.add_subplot(grid[row, col])
            ax.imshow(data[indices, :], interpolation="nearest", aspect="auto", cmap="gray", vmin=vmin, vmax=vmax)
            ax.set_yticks([])
            ax.grid(False)
            for spine in ("top", "right", "bottom"):
                ax.spines[spine].set_visible(False)
            ax.spines["left"].set_linewidth(3)
            ax.spines["left"].set_color(colors[row % len(colors)])
            if row < len(segments) - 1:
                ax.set_xticks([])
            else:
                ax.set_xticks(xticks, labels=xticklabels, fontsize=9)
                ax.set_xlabel("time (mm:ss)" if tr else "time-points (index)", fontsize=10)
            if row == 0:
                ax.set_title("preproc BOLD" if col == 0 else "clean BOLD", fontsize=13)
    handles = [Patch(color=colors[i % len(colors)], label=label) for i, label in enumerate(segments.keys())]
    fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 5), frameon=False, fontsize=10)
    fig.suptitle(title, fontsize=14)
    fig.subplots_adjust(left=0.05, right=0.98, top=0.92, bottom=0.09)
    fig.savefig(str(out))
    plt.close(fig)
    return out


def _write_single_qc_carpetplot(
    out: Path,
    carpet_data: np.ndarray,
    confounds: dict[str, np.ndarray],
    segments: dict[str, list[int]],
    layout: dict[str, object],
    tr: float,
    title: str,
    carpet_vminmax: tuple[float, float],
    signal_ylims: dict[str, tuple[float, float]],
) -> Path:
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec
    from matplotlib.patches import Patch
    from nireports.reportlets.nuisance import confoundplot

    out.parent.mkdir(parents=True, exist_ok=True)
    signal_labels = ["GS", "GSCSF", "GSWM", "DVARS", "FD"]
    plot_names = {"GS": "GS", "GSCSF": "CSF", "GSWM": "WM", "DVARS": "DVARS", "FD": "FD"}
    line_colors = {"GS": "#d62728", "GSCSF": "#9467bd", "GSWM": "#2ca02c", "DVARS": "#1f77b4", "FD": "#ff7f0e"}
    segment_colors = list(plt.get_cmap("Paired").colors)
    n_tp = carpet_data.shape[1]
    x = np.arange(n_tp) * tr if tr else np.arange(n_tp)
    fig = plt.figure(figsize=layout.get("figsize", (16.0, 13.5)), constrained_layout=False)
    grid = GridSpec(
        6,
        1,
        figure=fig,
        height_ratios=layout.get("height_ratios", [0.64, 0.64, 0.64, 0.64, 0.64, 8.0]),
        hspace=float(layout.get("hspace", 0.06)),
    )
    fig.subplots_adjust(
        left=float(layout.get("left", 0.08)),
        right=float(layout.get("right", 0.98)),
        top=float(layout.get("top", 0.96)),
        bottom=0.115,
    )
    for idx, label in enumerate(signal_labels):
        confoundplot(
            confounds[label],
            grid[idx, 0],
            name=plot_names[label],
            tr=tr,
            hide_x=True,
            color=line_colors[label],
            ylims=signal_ylims.get(label),
        )
    carpet_grid = GridSpecFromSubplotSpec(
        len(segments),
        1,
        subplot_spec=grid[5, 0],
        hspace=0.05,
        height_ratios=[max(1, len(v)) for v in segments.values()],
    )
    vmin, vmax = carpet_vminmax
    xticks = np.linspace(0, n_tp - 1, endpoint=True, num=7)
    if tr:
        xticklabels = [f"{t // 60:02d}:{t % 60:02d}" for t in np.rint(tr * xticks).astype(int)]
    else:
        xticklabels = [str(int(t)) for t in np.rint(xticks).astype(int)]
    last_ax = None
    for row, (label, indices) in enumerate(segments.items()):
        ax = fig.add_subplot(carpet_grid[row, 0])
        ax.imshow(carpet_data[indices, :], interpolation="nearest", aspect="auto", cmap="gray", vmin=vmin, vmax=vmax)
        ax.set_yticks([])
        ax.grid(False)
        for spine in ("top", "right", "bottom"):
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_linewidth(3)
        ax.spines["left"].set_color(segment_colors[row % len(segment_colors)])
        ax.spines["left"].set_position(("outward", 2))
        if row < len(segments) - 1:
            ax.set_xticks([])
        else:
            ax.set_xticks(xticks, labels=xticklabels, fontsize=11)
            ax.set_xlabel("time (mm:ss)" if tr else "time-points (index)", fontsize=12)
            ax.spines["bottom"].set_visible(True)
            ax.spines["bottom"].set_color("k")
            ax.spines["bottom"].set_linewidth(0.8)
        last_ax = ax
    if last_ax is not None:
        handles = [Patch(color=segment_colors[i % len(segment_colors)], label=label) for i, label in enumerate(segments.keys())]
        fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.040), ncol=min(len(handles), 5), frameon=False, fontsize=12)
    fig.text(0.5, 0.014, title, ha="center", va="bottom", fontsize=13)
    fig.savefig(str(out))
    plt.close(fig)
    return out


def plot_clean_carpet(ctx: RunContext, clean_bold: Path, base: str, tr: float, confounds_tsv: Path | None = None) -> Path | None:
    session = session_from_bold_base(base)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception as exc:
        write_text(ctx.output_subject / session / "qc_statistics" / f"{base}_desc-cleanCarpetplot_STATUS.txt", f"无法导入 matplotlib carpet plot: {type(exc).__name__}: {exc}")
        return None
    try:
        clean_img, data = load_bold(clean_bold)
        n_tp = data.shape[-1]
        preproc_bold = _find_preproc_bold_for_base(ctx, base)
        pre_carpet_data = np.empty((0, n_tp), dtype=np.float32)
        pre_tissue: dict[str, np.ndarray | None] = {"CSF": None, "WM": None}
        pre_tissue_sources = {"CSF": "", "WM": ""}
        shared_mask_voxels = 0
        if preproc_bold is not None:
            pre_img, pre_data = load_bold(preproc_bold)
            pre_tissue, pre_tissue_sources = tissue_signals_for_bold(ctx, pre_img, pre_data, base)
            pre_carpet_data, carpet_data, _shared_mask = _common_valid_carpet_data(pre_data, data)
            shared_mask_voxels = int(_shared_mask.sum())
        else:
            flat = data.reshape(-1, data.shape[-1])
            mask = np.nanstd(flat, axis=1) > 0
            carpet_data = flat[mask].astype(np.float32)
            shared_mask_voxels = int(mask.sum())
        gs = np.nanmean(carpet_data, axis=0)
        confounds = {
            "GS": gs,
            "DVARS": _dvars_from_carpet_data(carpet_data),
            "FD": _confound_series(confounds_tsv, "FD", n_tp),
        }
        tissue_signals, tissue_sources = clean_tissue_signals(ctx, clean_bold, base, data, confounds_tsv)
        confounds["GSCSF"] = tissue_signals["CSF"]
        confounds["GSWM"] = tissue_signals["WM"]
        if pre_carpet_data.size:
            pre_confounds = {
                "GS": np.nanmean(pre_carpet_data, axis=0),
                "DVARS": _dvars_from_carpet_data(pre_carpet_data),
                "FD": _confound_series(confounds_tsv, "FD", n_tp),
                "GSCSF": pre_tissue["CSF"] if pre_tissue["CSF"] is not None else _confound_series(confounds_tsv, "GSCSF", n_tp),
                "GSWM": pre_tissue["WM"] if pre_tissue["WM"] is not None else _confound_series(confounds_tsv, "GSWM", n_tp),
            }
        else:
            pre_confounds = {
                "GS": _confound_series(confounds_tsv, "global_signal", n_tp),
                "DVARS": _confound_series(confounds_tsv, "DVARS", n_tp),
                "FD": _confound_series(confounds_tsv, "FD", n_tp),
                "GSCSF": _confound_series(confounds_tsv, "GSCSF", n_tp),
                "GSWM": _confound_series(confounds_tsv, "GSWM", n_tp),
            }
        signal_sources = {
            "GS": "clean BOLD brain-mask mean, recomputed",
            "GSCSF": tissue_sources["CSF"],
            "GSWM": tissue_sources["WM"],
            "DVARS": "clean BOLD voxelwise temporal difference RMS, recomputed",
            "FD": "fMRIPrep framewise_displacement; motion estimate is not recomputed from BOLD",
        }
        comparison_csv, comparison_json = write_carpetplot_signal_comparison(
            ctx,
            base,
            tr,
            confounds_tsv,
            confounds,
            tissue_sources,
            carpet_data,
            pre_carpet_data=pre_carpet_data,
            preproc_bold_path=preproc_bold,
            pre_tissue=pre_tissue,
            pre_tissue_sources=pre_tissue_sources,
        )
        confound_stats = {label: _series_stats(values) for label, values in confounds.items()}
        max_voxels = int(os.environ.get("FMRI_CARPET_MAX_VOXELS", "60000"))
        if carpet_data.shape[0] > max_voxels:
            idx = np.linspace(0, carpet_data.shape[0] - 1, max_voxels).astype(int)
            carpet_data = carpet_data[idx]
            if pre_carpet_data.size:
                pre_carpet_data = pre_carpet_data[idx]
        fmriprep_labels, fmriprep_weights, fmriprep_layout, fmriprep_svg = _fmriprep_carpetplot_format(ctx, base)
        if fmriprep_labels and fmriprep_weights is not None:
            carpet_segments = _segments_from_weights(carpet_data.shape[0], fmriprep_labels, fmriprep_weights)
        else:
            carpet_segments = _fmriprep_style_segments(carpet_data.shape[0])
        out = ctx.output_subject / session / "qc_statistics" / f"{qc_bold_base(base)}_desc-carpetplot_bold.svg"
        pre_out = out.with_name(out.name.replace("_desc-carpetplot_bold.svg", "_desc-preprocCarpetplot_bold.svg"))
        out.parent.mkdir(parents=True, exist_ok=True)
        plt.rcParams.update(
            {
                "font.size": 24,
                "axes.labelsize": 18,
                "xtick.labelsize": 14,
                "ytick.labelsize": 14,
                "legend.fontsize": 16,
                "svg.fonttype": "path",
            }
        )
        x = np.arange(n_tp) * tr if tr else np.arange(n_tp)
        signal_labels = ["GS", "GSCSF", "GSWM", "DVARS", "FD"]
        signal_csv = out.with_name(out.name.replace("_desc-carpetplot_bold.svg", "_desc-carpetplot_timeseries.csv"))
        with signal_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["frame", "time_seconds", *[f"pre_{label}" for label in signal_labels], *[f"post_{label}" for label in signal_labels]])
            for frame in range(n_tp):
                writer.writerow([frame, float(x[frame]), *[float(pre_confounds[label][frame]) for label in signal_labels], *[float(confounds[label][frame]) for label in signal_labels]])
        signal_ylims: dict[str, tuple[float, float]] = {}
        for label in signal_labels:
            combined = np.concatenate([np.asarray(pre_confounds[label], dtype=np.float32), np.asarray(confounds[label], dtype=np.float32)])
            lo, hi = np.nanpercentile(combined, [1, 99])
            if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
                lo, hi = float(np.nanmin(combined)), float(np.nanmax(combined))
            pad = (hi - lo) * 0.08 if hi > lo else 1.0
            signal_ylims[label] = (float(lo - pad), float(hi + pad))
        prepost_svg = ""
        if pre_carpet_data.size:
            pre_plot_data, post_plot_data = _percent_signal_change(pre_carpet_data, carpet_data)
            vmin, vmax = np.nanpercentile(np.concatenate([pre_plot_data, post_plot_data], axis=1), [2, 98])
            if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
                vmin, vmax = -1.0, 1.0
            _write_single_qc_carpetplot(
                pre_out,
                pre_plot_data,
                pre_confounds,
                carpet_segments,
                fmriprep_layout,
                tr,
                f"{qc_bold_base(base)} preproc BOLD",
                (float(vmin), float(vmax)),
                signal_ylims,
            )
            _write_single_qc_carpetplot(
                out,
                post_plot_data,
                confounds,
                carpet_segments,
                fmriprep_layout,
                tr,
                f"{qc_bold_base(base)} clean BOLD",
                (float(vmin), float(vmax)),
                signal_ylims,
            )
            prepost_svg = str(pre_out)
        else:
            _write_single_qc_carpetplot(
                out,
                carpet_data,
                confounds,
                carpet_segments,
                fmriprep_layout,
                tr,
                f"{qc_bold_base(base)} clean BOLD",
                tuple(float(v) for v in np.nanpercentile(carpet_data, [2, 98])),
                signal_ylims,
            )
        write_json(
            out.with_suffix(".json"),
            {
                "source_clean_bold": str(clean_bold),
                "source_preproc_bold": str(preproc_bold) if preproc_bold else "",
                "source_confounds": str(confounds_tsv) if confounds_tsv else "",
                "timeseries_csv": str(signal_csv),
                "signal_comparison_csv": str(comparison_csv),
                "signal_comparison_json": str(comparison_json),
                "preproc_same_mask_svg": prepost_svg,
                "clean_same_mask_svg": str(out),
                "signals": signal_labels,
                "signal_sources": signal_sources,
                "signal_stats": confound_stats,
                "shared_mask_voxels": shared_mask_voxels,
                "source_fmriprep_carpetplot": str(fmriprep_svg) if fmriprep_svg else "",
                "carpet_segments": list(carpet_segments.keys()),
                "style": "qc_statistics writes separate preproc and clean SVGs using the same valid brain mask, segment heights, signal y-limits, and carpet intensity scale; fMRIPrep SVG is used only for layout proportions when available, not for numeric comparison",
            },
        )
        return out
    except Exception as exc:
        write_text(ctx.output_subject / session / "qc_statistics" / f"{qc_bold_base(base)}_desc-carpetplot_STATUS.txt", f"clean_data carpet plot 失败: {type(exc).__name__}: {exc}")
        return None


def plot_clean_carpet_legacy(ctx: RunContext, clean_bold: Path, base: str, tr: float) -> Path | None:
    session = session_from_bold_base(base)
    try:
        from nireports.reportlets.nuisance import plot_carpet
        _, data = load_bold(clean_bold)
        flat = data.reshape(-1, data.shape[-1])
        mask = np.nanstd(flat, axis=1) > 0
        carpet_data = flat[mask]
        out = ctx.output_subject / session / "qc_statistics" / f"{base}_desc-cleanCarpetplot_bold.svg"
        plot_carpet(
            carpet_data,
            tr=tr,
            title=f"{base} clean_data carpetplot",
            output_file=str(out),
            sort_rows=False,
            legend=False,
        )
        return out
    except Exception as exc:
        write_text(ctx.output_subject / session / "qc_statistics" / f"{base}_desc-cleanCarpetplot_STATUS.txt", f"clean_data carpet plot 失败: {type(exc).__name__}: {exc}")
        return None


def sleep_label_path(ctx: RunContext, session: str) -> Path | None:
    candidates = [
        ctx.input_subject / session / "sleep_label.csv",
        ctx.input_subject / session / "label" / "sleep_label.csv",
    ]
    return next((path for path in candidates if path.exists()), None)


def normalize_sleep_stage(value: object) -> str:
    stage = str(value).strip().upper()
    if stage == "W":
        return "W"
    if stage in {"S", "N1", "N2", "N3", "N4", "R", "REM"}:
        return "S"
    return "UNKNOWN"


def load_sleep_stage_segments(ctx: RunContext, session: str, n_tp: int, tr: float = 2.0, window: int = 4, sleep_stage_window: float = 30.0) -> tuple[list[dict], Path | None, str]:
    label_path = sleep_label_path(ctx, session)
    if label_path is None:
        return [], None, f"未找到 {session}/sleep_label.csv，按要求跳过 segment。"
    df = pd.read_csv(label_path)
    if df.empty:
        return [], label_path, f"{label_path} 为空，跳过 segment。"
    stage_col = "final" if "final" in df.columns else next((col for col in ["stage", "sleep_stage", "annotation_y", "annotation_x"] if col in df.columns), "")
    if not stage_col:
        return [], label_path, f"{label_path} 缺少 final/stage/annotation 列，跳过 segment。"
    onsets = pd.to_numeric(df["onset"], errors="coerce").to_numpy(dtype=float) if "onset" in df.columns else np.arange(len(df), dtype=float) * sleep_stage_window
    stages = [normalize_sleep_stage(value) for value in df[stage_col].tolist()]
    segments: list[dict] = []
    counts = {"W": 0, "S": 0}
    index = 0
    while index <= len(stages) - window:
        block = stages[index : index + window]
        stage = block[0]
        if stage in counts and block.count(stage) == window and np.isfinite(onsets[index]):
            start = int(onsets[index] // tr)
            end = int((onsets[index] + window * sleep_stage_window) // tr)
            start = max(0, min(start, n_tp))
            end = max(start, min(end, n_tp))
            if end - start >= 2:
                name = f"{stage}_{counts[stage]}"
                segments.append({"stage": stage, "name": name, "start": start, "end": end, "epoch_start": index, "epoch_end": index + window - 1})
                counts[stage] += 1
            index += window
        else:
            index += 1
    status = f"使用 {label_path} 按 core Segment.sleep_stage_nifti 规则切分：{window} 个 30s epoch 为一段，TR={tr:g}s；W={counts['W']} 段，S={counts['S']} 段。"
    return segments, label_path, status


def write_segment_summary(ctx: RunContext, session: str, label_path: Path | None, segments: list[dict], status: str) -> None:
    write_text(ctx.output_subject / session / "segment" / "STATUS.txt", status)
    write_json(
        ctx.output_subject / session / "segment" / "segment_summary.json",
        {
            "sleep_label": str(label_path) if label_path else "",
            "segment_count": len(segments),
            "segments": segments,
            "method": "core-compatible contiguous sleep-stage windows; window=4 epochs, sleep_stage_window=30s, TR=2s",
        },
    )


def reset_segment_outputs(ctx: RunContext, session: str) -> None:
    for rel in ["clean_data", "clean_info"]:
        path = ctx.output_subject / session / "segment" / rel
        if path.exists():
            shutil.rmtree(path)


def segment_bold(ctx: RunContext, clean_bold: Path, tr: float = 2.0, window: int = 4) -> list[Path]:
    img, data = load_bold(clean_bold)
    base = standard_bold_base(clean_bold)
    session = session_from_bold_base(base)
    segments, label_path, status = load_sleep_stage_segments(ctx, session, data.shape[-1], tr=tr, window=window)
    write_segment_summary(ctx, session, label_path, segments, status)
    if not segments:
        return []
    out_dir = ctx.output_subject / session / "segment" / "clean_data" / "volume"
    info_dir = ctx.output_subject / session / "segment" / "clean_info" / "volume"
    outputs = []
    bad_epochs = np.zeros((1, data.shape[-1]), dtype=np.float32)
    for segment in segments:
        start, end = int(segment["start"]), int(segment["end"])
        seg = nib.Nifti1Image(data[..., start:end], img.affine, img.header)
        out = out_dir / f"{segment['name']}.nii.gz"
        info = info_dir / f"{segment['name']}.mat"
        out.parent.mkdir(parents=True, exist_ok=True)
        info.parent.mkdir(parents=True, exist_ok=True)
        nib.save(seg, str(out))
        savemat(info, {"info": {"bad_epochs": bad_epochs[..., start:end]}})
        outputs.extend([out, info])
    return outputs


def segment_surfaces(ctx: RunContext, clean_surfaces: list[Path], tr: float = 2.0, window: int = 4) -> list[Path]:
    outputs: list[Path] = []
    for src in clean_surfaces:
        session = session_from_bold_base(src.name)
        space_match = re.search(r"_space-([^_]+)_", src.name)
        hemi_match = re.search(r"_(lh|rh)_", src.name)
        space = space_match.group(1) if space_match else "unknown"
        hemi = hemi_match.group(1) if hemi_match else "hemi"
        gii = nib.load(str(src))
        data = np.vstack([arr.data.astype(np.float32) for arr in gii.darrays])
        segments, label_path, status = load_sleep_stage_segments(ctx, session, data.shape[0], tr=tr, window=window)
        if not segments:
            write_segment_summary(ctx, session, label_path, segments, status)
            continue
        bad_epochs = np.zeros((1, data.shape[0]), dtype=np.float32)
        for segment in segments:
            start, end = int(segment["start"]), int(segment["end"])
            out_data = ctx.output_subject / session / "segment" / "clean_data" / "surface" / space / f"{segment['name']}_{hemi}.mat"
            out_info = ctx.output_subject / session / "segment" / "clean_info" / "surface" / space / f"{segment['name']}_{hemi}.mat"
            out_data.parent.mkdir(parents=True, exist_ok=True)
            out_info.parent.mkdir(parents=True, exist_ok=True)
            savemat(out_data, {"data": data[start:end].T.astype(np.float32)})
            savemat(out_info, {"info": {"bad_epochs": bad_epochs[..., start:end]}})
            outputs.extend([out_data, out_info])
    return outputs


def time_frequency(ctx: RunContext, clean_bold: Path, tr: float) -> dict:
    _, data = load_bold(clean_bold)
    base = standard_bold_base(clean_bold)
    session = session_from_bold_base(base)
    flat = data.reshape(-1, data.shape[-1])
    mask = np.nanmean(flat, axis=1) > 0
    ts = np.nanmean(flat[mask], axis=0)
    fs = 1.0 / tr
    freqs, psd = signal.welch(ts, fs=fs, nperseg=min(256, len(ts)))
    low = (freqs >= 0.01) & (freqs <= 0.08)
    all_band = (freqs >= 0.01) & (freqs <= min(0.25, fs / 2))
    alff = float(np.sqrt(np.trapezoid(psd[low], freqs[low]))) if low.any() else float("nan")
    denom = float(np.sqrt(np.trapezoid(psd[all_band], freqs[all_band]))) if all_band.any() else float("nan")
    falff = alff / denom if denom and not np.isnan(denom) else float("nan")
    psd_csv = ctx.output_subject / session / "time_frequency" / f"{base}_global_signal_psd.csv"
    psd_csv.parent.mkdir(parents=True, exist_ok=True)
    with psd_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["frequency_hz", "power"])
        writer.writerows(zip(freqs.tolist(), psd.tolist()))
    metrics = {"TR": tr, "sampling_rate_hz": fs, "ALFF_0.01_0.08": alff, "fALFF_0.01_0.08_over_0.01_0.25": falff}
    write_json(ctx.output_subject / session / "time_frequency" / f"{base}_alff_falff_summary.json", metrics)
    fig_path = plot_alff_falff_timefreq(ctx, session, base, ts, freqs, psd, metrics, tr)
    metrics["time_frequency_figure"] = str(fig_path) if fig_path else ""
    write_json(ctx.output_subject / session / "time_frequency" / f"{base}_alff_falff_summary.json", metrics)
    return metrics


def plot_alff_falff_timefreq(
    ctx: RunContext,
    session: str,
    base: str,
    ts: np.ndarray,
    freqs: np.ndarray,
    psd: np.ndarray,
    metrics: dict,
    tr: float,
) -> Path | None:
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception as exc:
        write_text(ctx.output_subject / session / "time_frequency" / f"{base}_desc-alffFalffTimefreq_STATUS.txt", f"无法导入 matplotlib: {type(exc).__name__}: {exc}")
        return None

    out = ctx.output_subject / session / "time_frequency" / f"{base}_desc-alffFalffTimefreq.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    ts = np.asarray(ts, dtype=np.float32)
    ts = np.nan_to_num(ts, nan=0.0, posinf=0.0, neginf=0.0)
    centered = ts - float(np.nanmean(ts))
    fs = 1.0 / tr
    nperseg = max(8, min(64, len(centered)))
    noverlap = min(nperseg // 2, nperseg - 1)
    spec_freqs, spec_times, spec = signal.spectrogram(centered, fs=fs, nperseg=nperseg, noverlap=noverlap, scaling="density", mode="psd")
    spec = np.nan_to_num(spec, nan=0.0, posinf=0.0, neginf=0.0)
    spec_db = 10.0 * np.log10(spec + np.finfo(np.float32).eps)
    spec_mask = spec_freqs <= min(0.25, fs / 2)

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig = plt.figure(figsize=(12, 7), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, width_ratios=[0.8, 1.8])
    ax_metric = fig.add_subplot(grid[:, 0])
    ax_psd = fig.add_subplot(grid[0, 1])
    ax_spec = fig.add_subplot(grid[1, 1])

    values = [
        float(metrics.get("ALFF_0.01_0.08", np.nan)),
        float(metrics.get("fALFF_0.01_0.08_over_0.01_0.25", np.nan)),
    ]
    bars = ax_metric.bar(["ALFF", "fALFF"], values, color=["#3b82f6", "#f97316"], width=0.55)
    ax_metric.set_title("ALFF / fALFF")
    ax_metric.set_ylabel("Value")
    for bar, value in zip(bars, values):
        ax_metric.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{value:.4g}", ha="center", va="bottom")

    ax_psd.plot(freqs, psd, color="#111827", linewidth=1.4)
    ax_psd.axvspan(0.01, 0.08, color="#93c5fd", alpha=0.35)
    ax_psd.set_xlim(0, min(0.25, fs / 2))
    ax_psd.set_title("Global signal PSD")
    ax_psd.set_xlabel("Frequency (Hz)")
    ax_psd.set_ylabel("Power")

    if spec_mask.any():
        mesh = ax_spec.pcolormesh(spec_times, spec_freqs[spec_mask], spec_db[spec_mask], shading="auto", cmap="magma")
        fig.colorbar(mesh, ax=ax_spec, label="Power (dB)")
    ax_spec.axhspan(0.01, 0.08, color="#93c5fd", alpha=0.18)
    ax_spec.set_title("Time-frequency spectrogram")
    ax_spec.set_xlabel("Time (s)")
    ax_spec.set_ylabel("Frequency (Hz)")

    fig.suptitle(f"{ctx.subject} {session} {base}", fontsize=13)
    fig.savefig(out, format="svg")
    plt.close(fig)
    return out


def qc_statistics(ctx: RunContext, fmriprep_status: dict, tf_metrics: dict) -> None:
    palm = shutil.which("palm")
    summary = {
        "subject": ctx.subject,
        "input": str(ctx.input_subject),
        "output": str(ctx.output_subject),
        "fmriprep": fmriprep_status,
        "palm_available": bool(palm),
        "palm_reason": "未找到 palm 命令，PALM 统计只保留空目录和说明。" if not palm else f"palm: {palm}",
        "time_frequency": tf_metrics,
    }
    write_json(ctx.output_subject / "logs" / "qc_summary.json", summary)
    write_text(
        ctx.output_subject / "logs" / "PALM_STATUS.txt",
        summary["palm_reason"],
    )


def main() -> int:
    log_step("analysis: 启动分层 fMRI skill 分析流程")
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    subject, input_subject = choose_subject()
    log_step(f"analysis: 选择被试 {subject}, 输入目录 {input_subject}")
    output_subject = DERIVATIVES_ROOT / subject
    if output_subject.exists() and os.environ.get("FMRI_CLEAN_OUTPUT", "0") == "1":
        log_step(f"analysis: 清理旧输出 {output_subject}")
        shutil.rmtree(output_subject)
    ctx = RunContext(
        subject=subject,
        input_subject=input_subject,
        output_subject=output_subject,
        bids_root=OUTPUT_ROOT,
        report={"subject": subject, "steps": {}},
    )
    ensure_dirs(ctx)
    for session in sorted(selected_session_names(ctx.input_subject)):
        ensure_session_analysis_dirs(ctx, session)
    prune_legacy_top_level_dirs(ctx)
    try:
        started = time.monotonic()
        log_step("step: BIDS 整理开始")
        _, bolds = prepare_bids(ctx)
        finish_step("step: BIDS 整理", started)
        if os.environ.get("FMRI_BIDS_ONLY", "0") == "1":
            write_text(ctx.output_subject / "STATUS.txt", "BIDS 整理已完成；FMRI_BIDS_ONLY=1，未运行 fMRIPrep 和后续分析。")
            write_json(ctx.output_subject / "logs" / "layered_skill_test_report.json", ctx.report)
            log_step(f"analysis: BIDS-only 完成，输出目录 {ctx.bids_root}")
            return 0
        if not bolds:
            raise FileNotFoundError("没有可用 BOLD NIfTI，无法继续后续层。")

        started = time.monotonic()
        log_step("step: fMRIPrep 尝试/复用开始")
        fmriprep_status = attempt_fmriprep(ctx)
        finish_step("step: fMRIPrep 尝试/复用", started)

        started = time.monotonic()
        log_step("step: 定位 fMRIPrep 输出开始")
        located = locate_fmriprep_outputs(ctx)
        bold_runs = locate_fmriprep_bold_runs(ctx)
        finish_step("step: 定位 fMRIPrep 输出", started)
        if fmriprep_status.get("returncode") == 0 and bold_runs:
            processed_runs = []
            all_surface_files = []
            surface_clean = []
            first_clean = None
            first_tr = 2.0
            copied_figures = copy_selected_fmriprep_figures(ctx)
            prune_unselected_fmriprep_session_dirs(ctx)
            for run in bold_runs:
                preproc_bold = Path(run["preproc_bold"])
                confounds_tsv = Path(run["confounds"])
                base = standard_bold_base(preproc_bold)
                session = session_from_bold_base(base)
                log_step(f"step: 构建正式回归器 {base}")
                started = time.monotonic()
                conf_path, reg_path, regressors, tr = build_regressors_from_fmriprep(ctx, confounds_tsv, preproc_bold)
                finish_step("step: fMRIPrep confounds/regressors", started)
                _, preproc_data = load_bold(preproc_bold)
                mask = np.nanmean(preproc_data.reshape(-1, preproc_data.shape[-1]), axis=1) != 0
                clean_path = ctx.output_subject / session / "clean_data" / "volume" / f"{base}_12rp_50pca_csf_wm.nii.gz"
                started = time.monotonic()
                log_step(f"step: volume 去噪 {base}")
                clean = denoise_bold(ctx, preproc_bold, regressors, mask, clean_path)
                finish_step("step: volume 去噪", started)
                stat_csv, bad_json = compute_outliers(ctx, clean, confounds_tsv, base)
                carpet = plot_clean_carpet(ctx, clean, base, tr, confounds_tsv)
                processed_runs.append(
                    {
                        "base": base,
                        "session": session,
                        "preproc_bold": str(preproc_bold),
                        "confounds": str(conf_path),
                        "regressors": str(reg_path),
                        "clean_bold": str(clean),
                        "outlier_stat": str(stat_csv),
                        "bad_epoch_info": str(bad_json),
                        "clean_carpetplot": str(carpet) if carpet else "",
                        "tr": tr,
                    }
                )
                run_surface_files = [Path(p) for p in run.get("surface_bold", [])]
                all_surface_files.extend(run_surface_files)
                run_surface_clean = denoise_surfaces(ctx, run_surface_files, regressors)
                if not run_surface_files:
                    fallback_clean, fallback_sources = project_clean_bold_to_fsnative_surfaces(ctx, clean, base)
                    run_surface_clean.extend(fallback_clean)
                    all_surface_files.extend(fallback_sources)
                surface_clean.extend(run_surface_clean)
                if first_clean is None:
                    first_clean = clean
                    first_tr = tr
            clean = first_clean
            tr = first_tr
            conf_path = Path(processed_runs[0]["confounds"])
            reg_path = Path(processed_runs[0]["regressors"])
            stat_csv = Path(processed_runs[0]["outlier_stat"])
            bad_json = Path(processed_runs[0]["bad_epoch_info"])
            started = time.monotonic()
            log_step("step: surface_transform 整理开始")
            surface_transform = organize_surface_transform(ctx, all_surface_files)
            finish_step("step: surface_transform 整理", started)
        else:
            reason = (
                "fMRIPrep 未完整完成，停止后续 confounds/regressors、去噪、分段、时频和 QC。"
                " 请先修复 fMRIPrep，确保返回码为 0 且生成 desc-preproc_bold.nii.gz 与 desc-confounds_timeseries.tsv。"
            )
            write_text(ctx.output_subject / "STATUS.txt", reason)
            write_json(ctx.output_subject / "logs" / "layered_skill_test_report.json", ctx.report)
            log_step("analysis: " + reason)
            return 2

        if clean is None:
            raise RuntimeError("没有生成 clean_data，无法继续分段和时频分析。")

        started = time.monotonic()
        log_step("step: 分段开始")
        segments = []
        for session in sorted({run["session"] for run in processed_runs}):
            reset_segment_outputs(ctx, session)
        for run in processed_runs:
            run_clean = Path(run["clean_bold"])
            segments.extend(segment_bold(ctx, run_clean, tr=float(run.get("tr") or tr)))
        surface_segments = segment_surfaces(ctx, surface_clean, tr=tr)
        finish_step("step: 分段", started)

        started = time.monotonic()
        log_step("step: 时频分析开始")
        tf_metrics_by_run = {}
        for run in processed_runs:
            run_clean = Path(run["clean_bold"])
            tf_metrics_by_run[run["base"]] = time_frequency(ctx, run_clean, float(run.get("tr") or tr))
        tf_metrics = {"runs": tf_metrics_by_run}
        finish_step("step: 时频分析", started)

        started = time.monotonic()
        log_step("step: QC/statistics 汇总开始")
        qc_statistics(ctx, fmriprep_status, tf_metrics)
        finish_step("step: QC/statistics 汇总", started)
        ctx.report["steps"] = {
            "selected_subject": subject,
            "bold_used": str(bolds[0]),
            "confounds": str(conf_path),
            "regressors": str(reg_path),
            "clean_bold": str(clean),
            "surface_transform": [str(p) for p in surface_transform],
            "clean_surface": [str(p) for p in surface_clean],
            "figures": [str(p) for p in copied_figures],
            "processed_runs": processed_runs,
            "outlier_stat": str(stat_csv),
            "bad_epoch_info": str(bad_json),
            "segments": [str(p) for p in segments],
            "surface_segments": [str(p) for p in surface_segments],
            "fmriprep_status": fmriprep_status,
        }
        write_text(ctx.output_subject / "STATUS.txt", "分层 skill 分析流程已完成。不可实现的层已保留空目录并写明原因。")
        write_json(ctx.output_subject / "logs" / "layered_skill_test_report.json", ctx.report)
        log_step(f"analysis: 全流程完成，输出目录 {ctx.output_subject}")
        return 0
    except Exception as exc:
        write_text(ctx.output_subject / "logs" / "ERROR.txt", f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")
        write_json(ctx.output_subject / "logs" / "layered_skill_test_report.json", ctx.report)
        log_step(f"analysis: 失败 {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
