#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import grp
import gzip
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE_TEST_INPUT = Path(os.environ.get("FMRI_INPUT_SUBJECT", "/data/input/sub-YZ1"))
DEFAULT_OUTPUT = Path(os.environ.get("FMRI_FASTSURFER_OUTPUT_ROOT", "/outputs/fmri_fast/sub-YZ1/fmriprep"))
DEFAULT_FASTSURFER_IMAGE = "deepmi/fastsurfer:latest"
DEFAULT_FS_LICENSE = ROOT / "tools" / "license.txt"
LOCAL_AGENT_PYTHON = Path("/opt/anaconda3/envs/agent/bin/python")
DEFAULT_AGENT_PYTHON = Path(os.environ.get("FMRI_AGENT_PYTHON", str(LOCAL_AGENT_PYTHON if LOCAL_AGENT_PYTHON.exists() else "python")))
DEFAULT_FMRIPREP_RUNNER = ROOT / "run_fmriprep_nomgr.py"


def default_templateflow_home() -> Path:
    configured = os.environ.get("TEMPLATEFLOW_HOME", "").strip()
    fallback = Path.home() / ".cache" / "templateflow"
    if not configured:
        return fallback
    path = Path(configured)
    if path == Path("/templateflow") and (not path.exists() or not os.access(path, os.W_OK)):
        return fallback
    return path


DEFAULT_TEMPLATEFLOW = default_templateflow_home()
_USE_SG_DOCKER: bool | None = None


@dataclass
class Context:
    subject: str
    fs_subject: str
    session: str
    input_subject: Path
    output_root: Path
    bids_root: Path
    fastsurfer_subjects_dir: Path
    fs_license: Path
    fastsurfer_image: str
    agent_python: Path
    fmriprep_runner: Path
    templateflow: Path


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_capture(cmd: list[str], log_path: Path | None = None, timeout: int | None = None) -> dict:
    result = {
        "cmd": cmd,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "error": "",
    }
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        result.update({"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    if log_path:
        write_json(log_path, result)
    return result


def user_in_group(group_name: str) -> bool:
    try:
        group = grp.getgrnam(group_name)
    except KeyError:
        return False
    username = getpass.getuser()
    return username in group.gr_mem or os.getgid() == group.gr_gid


def use_sg_docker() -> bool:
    global _USE_SG_DOCKER
    requested = os.environ.get("FMRI_USE_SG_DOCKER", "auto").lower()
    if requested in {"1", "true", "yes"}:
        return True
    if requested in {"0", "false", "no"}:
        return False
    if _USE_SG_DOCKER is not None:
        return _USE_SG_DOCKER
    direct = subprocess.run(["docker", "images"], text=True, capture_output=True)
    _USE_SG_DOCKER = direct.returncode != 0 and shutil.which("sg") is not None and user_in_group("docker")
    return _USE_SG_DOCKER


def docker_cmd(args: list[str]) -> list[str]:
    cmd = ["docker", *args]
    if use_sg_docker():
        return ["sg", "docker", "-c", shlex.join(cmd)]
    return cmd


def docker_host_path(path: Path) -> str:
    resolved = path.resolve()
    mappings = [
        (Path("/outputs"), os.environ.get("FMRI_DOCKER_HOST_OUTPUT_ROOT", "")),
        (Path("/data"), os.environ.get("FMRI_DOCKER_HOST_DATA_ROOT", "")),
        (Path("/licenses"), os.environ.get("FMRI_DOCKER_HOST_LICENSE_DIR", "")),
        (Path("/templateflow"), os.environ.get("FMRI_DOCKER_HOST_TEMPLATEFLOW_ROOT", "")),
    ]
    for container_root, host_root in mappings:
        if not host_root:
            continue
        try:
            relative = resolved.relative_to(container_root)
        except ValueError:
            continue
        return str(Path(host_root).expanduser().resolve() / relative)
    return str(resolved)


def run_streaming(cmd: list[str], log_path: Path, env: dict[str, str] | None = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    with log_path.open("w", encoding="utf-8") as log:
        log.write("COMMAND:\n" + " ".join(cmd) + "\n\nOUTPUT:\n")
        log.flush()
        proc = subprocess.Popen(cmd, text=True, stdout=log, stderr=subprocess.STDOUT, env=merged_env)
        returncode = proc.wait()
        log.write(f"\n\nRETURN_CODE: {returncode}\n")
    return int(returncode)


def ensure_writable_dir(path: Path) -> None:
    if path.exists() and os.access(path, os.W_OK):
        return
    if path.exists():
        try:
            if not any(path.iterdir()):
                path.rmdir()
        except Exception as exc:
            raise PermissionError(f"目录不可写且无法清理：{path} ({type(exc).__name__}: {exc})") from exc
    path.mkdir(parents=True, exist_ok=True)
    if not os.access(path, os.W_OK):
        raise PermissionError(f"目录不可写：{path}")


def ensure_freesurfer_surface_compat(subject_dir: Path) -> dict[str, object]:
    surf = subject_dir / "surf"
    fixed: list[str] = []
    missing: list[str] = []
    for hemi in ("lh", "rh"):
        white = surf / f"{hemi}.white"
        pial = surf / f"{hemi}.pial"
        pial_t1 = surf / f"{hemi}.pial.T1"
        if not white.exists():
            missing.append(str(white))
        if not pial.exists() and pial_t1.exists():
            try:
                os.symlink(pial_t1.name, pial)
                fixed.append(str(pial))
            except FileExistsError:
                pass
            except OSError:
                shutil.copyfile(pial_t1, pial)
                fixed.append(str(pial))
        if not pial.exists():
            missing.append(str(pial))
    status = {"subject_dir": str(subject_dir), "fixed": fixed, "missing": missing, "compatible": not missing}
    write_json(subject_dir / "scripts" / "fmriprep_surface_compat.json", status)
    return status


def fastsurfer_subject_compatible(subject_dir: Path) -> bool:
    if not subject_dir.exists():
        return False
    required_dirs = [subject_dir / "mri", subject_dir / "surf", subject_dir / "scripts"]
    if not all(path.exists() for path in required_dirs):
        return False
    return bool(ensure_freesurfer_surface_compat(subject_dir).get("compatible"))


def quarantine_incomplete_fastsurfer_subject(subject_dir: Path) -> dict[str, object]:
    status: dict[str, object] = {
        "subject_dir": str(subject_dir),
        "exists": subject_dir.exists(),
        "compatible": False,
        "moved_to": "",
        "skipped": False,
        "reason": "",
    }
    if not subject_dir.exists():
        status["reason"] = "未发现 FastSurfer subject 目录。"
        return status
    status["compatible"] = fastsurfer_subject_compatible(subject_dir)
    if status["compatible"]:
        status["reason"] = "FastSurfer subject 已兼容 fMRIPrep。"
        return status
    if os.environ.get("FMRIPREP_QUARANTINE_INCOMPLETE_FS", "1") != "1":
        status["skipped"] = True
        status["reason"] = "FMRIPREP_QUARANTINE_INCOMPLETE_FS=0，保留不完整 FastSurfer subject。"
        return status
    suffix = time.strftime("%Y%m%d-%H%M%S")
    backup = subject_dir.with_name(f"{subject_dir.name}.incomplete-{suffix}")
    counter = 1
    while backup.exists():
        backup = subject_dir.with_name(f"{subject_dir.name}.incomplete-{suffix}-{counter}")
        counter += 1
    shutil.move(str(subject_dir), str(backup))
    status["moved_to"] = str(backup)
    status["reason"] = "已隔离不完整 FastSurfer subject；下一次将重新生成。"
    return status


def copy_or_gzip_nii(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.name.endswith(".nii.gz"):
        shutil.copyfile(src, dst)
    elif src.suffix == ".nii":
        with src.open("rb") as f_in, gzip.open(dst, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    else:
        shutil.copyfile(src, dst)


def find_json_for(nii: Path) -> Path | None:
    stem = nii.name.removesuffix(".nii.gz").removesuffix(".nii")
    candidate = nii.with_name(stem + ".json")
    if candidate.exists():
        return candidate
    jsons = sorted(nii.parent.glob("*.json"))
    return jsons[0] if jsons else None


def find_session_dir(input_subject: Path, session: str) -> Path:
    direct = input_subject / session
    if direct.is_dir():
        return direct
    matches = []
    for path in sorted(input_subject.rglob(session)):
        if not path.is_dir() or any(part.startswith(".") for part in path.parts):
            continue
        if (path / "anat").is_dir() or (path / "func").is_dir():
            matches.append(path)
    if matches:
        return matches[0]
    return direct


def find_first_t1(input_subject: Path, session: str) -> Path:
    anat_root = find_session_dir(input_subject, session) / "anat"
    candidates = sorted(anat_root.glob("*T1*/**/*.nii.gz")) + sorted(anat_root.glob("*T1*/**/*.nii"))
    if not candidates:
        raise FileNotFoundError(f"未找到 T1w NIfTI: {anat_root}")
    return candidates[0]


def find_first_bold(input_subject: Path, session: str) -> Path | None:
    func_root = find_session_dir(input_subject, session) / "func"
    candidates = sorted(func_root.glob("*/**/*.nii.gz")) + sorted(func_root.glob("*/**/*.nii"))
    if not candidates:
        return None
    return candidates[0]


def convert_first_bold_dicom(ctx: Context, func_dir: Path, bids_stem: str) -> Path:
    func_root = find_session_dir(ctx.input_subject, ctx.session) / "func"
    dcm_series = sorted(p for p in func_root.iterdir() if p.is_dir() and any(p.glob("*.dcm")))
    if not dcm_series:
        raise FileNotFoundError(f"未找到 BOLD NIfTI 或 DICOM series: {func_root}")
    dcm2niix = shutil.which("dcm2niix") or os.environ.get("DCM2NIIX", "/usr/bin/dcm2niix")
    if not Path(dcm2niix).exists():
        raise FileNotFoundError("未找到 dcm2niix，无法从 DICOM 转换 BOLD。")
    func_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [dcm2niix, "-z", "y", "-f", bids_stem, "-o", str(func_dir), str(dcm_series[0])],
        text=True,
        capture_output=True,
        env={
            **os.environ.copy(),
            "PATH": os.environ.get("PATH", ""),
        },
    )
    write_text(
        ctx.output_root / "logs" / "dcm2niix_bold.log",
        "COMMAND:\n"
        + " ".join([dcm2niix, "-z", "y", "-f", bids_stem, "-o", str(func_dir), str(dcm_series[0])])
        + "\n\nSTDOUT:\n"
        + proc.stdout
        + "\n\nSTDERR:\n"
        + proc.stderr
        + f"\n\nRETURN_CODE: {proc.returncode}",
    )
    if proc.returncode != 0:
        raise RuntimeError("dcm2niix 转换 BOLD 失败，详见 logs/dcm2niix_bold.log")
    converted = sorted(func_dir.glob(f"{bids_stem}*.nii.gz")) + sorted(func_dir.glob(f"{bids_stem}*.nii"))
    if not converted:
        raise FileNotFoundError(f"dcm2niix 未生成 NIfTI: {func_dir}")
    return converted[0]


def prepare_minimal_bids(ctx: Context) -> tuple[Path, Path]:
    existing_t1 = sorted((ctx.bids_root / ctx.subject / ctx.session / "anat").glob("*_T1w.nii.gz"))
    existing_bold = sorted((ctx.bids_root / ctx.subject / ctx.session / "func").glob("*_bold.nii.gz"))
    if existing_t1:
        t1_path = existing_t1[0]
        bold_path = existing_bold[0] if existing_bold else t1_path
        write_text(ctx.output_root / "BIDS_STATUS.txt", f"复用已有主分析 BIDS。\nT1w: {t1_path}\nBOLD: {bold_path if existing_bold else '未检查'}")
        return t1_path, bold_path

    anat_dir = ctx.bids_root / ctx.subject / ctx.session / "anat"
    func_dir = ctx.bids_root / ctx.subject / ctx.session / "func"
    write_json(ctx.bids_root / "dataset_description.json", {"Name": "FastSurfer fMRIPrep integration test", "BIDSVersion": "1.8.0"})

    t1_dst = anat_dir / f"{ctx.subject}_{ctx.session}_T1w.nii.gz"
    bold_dst = func_dir / f"{ctx.subject}_{ctx.session}_task-sleep0_run-01_bold.nii.gz"
    t1_src = find_first_t1(ctx.input_subject, ctx.session)
    copy_or_gzip_nii(t1_src, t1_dst)
    bold_src = find_first_bold(ctx.input_subject, ctx.session)
    if bold_src:
        copy_or_gzip_nii(bold_src, bold_dst)
    else:
        bold_dst = convert_first_bold_dicom(ctx, func_dir, bold_dst.name.removesuffix(".nii.gz"))

    t1_json = find_json_for(t1_src)
    if t1_json:
        shutil.copyfile(t1_json, t1_dst.with_suffix("").with_suffix(".json"))
    bold_json = find_json_for(bold_src)
    meta = {}
    if bold_json:
        try:
            meta = json.loads(bold_json.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta["TaskName"] = "sleep0"
    write_json(bold_dst.with_suffix("").with_suffix(".json"), meta)
    write_text(ctx.output_root / "BIDS_STATUS.txt", f"T1w: {t1_dst}\nBOLD: {bold_dst}")
    return t1_dst, bold_dst


def docker_gpu_probe(ctx: Context) -> dict:
    checks = {
        "docker_version": run_capture(docker_cmd(["--version"])),
        "docker_images": run_capture(docker_cmd(["images"])),
        "host_nvidia_smi": run_capture(["nvidia-smi"]),
        "container_gpu": run_capture(docker_cmd(["run", "--rm", "--gpus", "all", "nvidia/cuda:12.2.0-base-ubuntu22.04", "nvidia-smi"]), timeout=60),
        "fastsurfer_help": run_capture(docker_cmd(["run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", ctx.fastsurfer_image, "--help"]), timeout=60),
    }
    write_json(ctx.output_root / "logs" / "doctor.json", checks)
    return checks


def fastsurfer_cmd(ctx: Context, t1_path: Path) -> list[str]:
    return docker_cmd([
        "run",
        "--gpus",
        "all",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--cpus",
        os.environ.get("FASTSURFER_CPUS", "24"),
        "--memory",
        os.environ.get("FASTSURFER_MEMORY", "64g"),
        "-v",
        f"{docker_host_path(ctx.bids_root)}:/data:ro",
        "-v",
        f"{docker_host_path(ctx.fastsurfer_subjects_dir)}:/output",
        "-v",
        f"{docker_host_path(ctx.fs_license.parent)}:/fs_license:ro",
        ctx.fastsurfer_image,
        "--fs_license",
        f"/fs_license/{ctx.fs_license.name}",
        "--t1",
        f"/data/{ctx.subject}/{ctx.session}/anat/{t1_path.name}",
        "--sid",
        ctx.fs_subject,
        "--sd",
        "/output",
        "--parallel",
        "--threads",
        os.environ.get("FASTSURFER_THREADS", "24"),
    ])


def fmriprep_cmd(ctx: Context) -> list[str]:
    fmriprep_output = ctx.output_root / "output" if ctx.output_root.name == "fmriprep" else ctx.output_root / "fmriprep"
    configured_work = os.environ.get("FMRIPREP_WORK_DIR", "").strip()
    if configured_work:
        fmriprep_work = Path(configured_work).expanduser() / ctx.subject
    else:
        fmriprep_work = ctx.bids_root.parent / "work" / ctx.bids_root.name / ctx.subject
    fmriprep_work.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ctx.agent_python if ctx.agent_python.exists() else Path(sys.executable)),
        str(ctx.fmriprep_runner),
        str(ctx.bids_root),
        str(fmriprep_output),
        "participant",
        "--participant-label",
        ctx.subject.replace("sub-", ""),
        "--skip-bids-validation",
        "--fs-license-file",
        str(ctx.fs_license),
        "--fs-subjects-dir",
        str(ctx.fastsurfer_subjects_dir),
        "--fs-no-reconall",
        "--fs-no-resume",
        "--output-spaces",
        *os.environ.get("FMRIPREP_OUTPUT_SPACES", "T1w MNI152NLin6Asym:res-2 MNI152NLin2009cAsym:res-2 fsnative fsaverage").split(),
        "--ignore",
        "slicetiming",
        "--nthreads",
        os.environ.get("FMRIPREP_NTHREADS", "8"),
        "--omp-nthreads",
        os.environ.get("FMRIPREP_OMP_NTHREADS", "2"),
        "--mem",
        os.environ.get("FMRIPREP_MEM_MB", "48000"),
        "--work-dir",
        str(fmriprep_work),
        "--stop-on-first-crash",
        "--no-track-sessions",
    ]
    if os.environ.get("FMRIPREP_NO_MSM", "1") != "0":
        cmd.insert(cmd.index("--output-spaces"), "--no-msm")
    extra_args = os.environ.get("FMRIPREP_EXTRA_ARGS", "")
    if extra_args:
        cmd.extend(shlex.split(extra_args))
    return cmd


def fmriprep_env(ctx: Context) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", ""),
        "MPLCONFIGDIR": "/tmp/matplotlib",
        "TEMPLATEFLOW_HOME": str(ctx.templateflow),
        "FREESURFER_HOME": os.environ.get("FREESURFER_HOME", "/usr/local/freesurfer/8.1.0"),
        "FREESURFER": os.environ.get("FREESURFER", os.environ.get("FREESURFER_HOME", "/usr/local/freesurfer/8.1.0")),
        "FSLOUTPUTTYPE": "NIFTI_GZ",
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "1"),
        "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS", "1"),
        "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS", "1"),
        "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS": os.environ.get("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS", "1"),
    }


def write_plan(ctx: Context, t1_path: Path) -> None:
    plan = {
        "bids_subject": ctx.subject,
        "fastsurfer_subject": ctx.fs_subject,
        "bids_root": str(ctx.bids_root),
        "input_subject": str(ctx.input_subject),
        "output_root": str(ctx.output_root),
        "fastsurfer_subjects_dir": str(ctx.fastsurfer_subjects_dir),
        "fastsurfer_command": fastsurfer_cmd(ctx, t1_path),
        "fmriprep_command": fmriprep_cmd(ctx),
        "notes": [
            "FastSurfer output is reused by fMRIPrep through --fs-subjects-dir.",
            "fMRIPrep uses --fs-no-resume to import the precomputed FreeSurfer-compatible subject.",
        ],
    }
    write_json(ctx.output_root / "command_plan.json", plan)


def run_fastsurfer(ctx: Context) -> int:
    t1_path, _ = prepare_minimal_bids(ctx)
    ensure_writable_dir(ctx.fastsurfer_subjects_dir)
    subject_dir = ctx.fastsurfer_subjects_dir / ctx.fs_subject
    quarantine = quarantine_incomplete_fastsurfer_subject(subject_dir)
    write_json(ctx.output_root / "fastsurfer_incomplete_subject_cleanup.json", quarantine)
    if quarantine.get("skipped") and quarantine.get("exists") and not quarantine.get("compatible"):
        write_text(ctx.output_root / "fastsurfer_STATUS.txt", str(quarantine.get("reason")))
        return 2
    write_plan(ctx, t1_path)
    cmd = fastsurfer_cmd(ctx, t1_path)
    returncode = run_streaming(cmd, ctx.output_root / "logs" / "fastsurfer_docker.log")
    status = {
        "returncode": returncode,
        "subject_dir": str(subject_dir),
        "quarantine": quarantine,
        "mri_exists": (subject_dir / "mri").exists(),
        "surf_exists": (subject_dir / "surf").exists(),
        "scripts_exists": (subject_dir / "scripts").exists(),
    }
    if returncode == 0 and status["surf_exists"]:
        status["surface_compat"] = ensure_freesurfer_surface_compat(subject_dir)
    write_json(ctx.output_root / "fastsurfer_status.json", status)
    return returncode


def run_fmriprep(ctx: Context) -> int:
    t1_path, _ = prepare_minimal_bids(ctx)
    write_plan(ctx, t1_path)
    subject_dir = ctx.fastsurfer_subjects_dir / ctx.fs_subject
    if not fastsurfer_subject_compatible(subject_dir):
        write_text(ctx.output_root / "fmriprep_STATUS.txt", f"缺少完整 FastSurfer subject 输出：{subject_dir}")
        return 2
    cmd = fmriprep_cmd(ctx)
    returncode = run_streaming(cmd, ctx.output_root / "logs" / "fmriprep_with_fastsurfer.log", env=fmriprep_env(ctx))
    write_text(ctx.output_root / "fmriprep_STATUS.txt", f"RETURN_CODE: {returncode}")
    return returncode


def build_context(args: argparse.Namespace) -> Context:
    default_bids_root = args.output_root / "bids_dataset" if args.output_root.name == "fmriprep" else args.output_root / "fmriprep" / "bids_dataset"
    bids_root = args.bids_root if args.bids_root else default_bids_root
    default_fastsurfer_subjects_dir = bids_root / "derivatives" / "FASTSURFER"
    return Context(
        subject=args.subject,
        fs_subject=args.fs_subject or args.subject,
        session=args.session,
        input_subject=args.input_subject,
        output_root=args.output_root,
        bids_root=bids_root,
        fastsurfer_subjects_dir=args.fastsurfer_subjects_dir if args.fastsurfer_subjects_dir else default_fastsurfer_subjects_dir,
        fs_license=args.fs_license,
        fastsurfer_image=args.fastsurfer_image,
        agent_python=args.agent_python,
        fmriprep_runner=args.fmriprep_runner,
        templateflow=args.templateflow,
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test Docker FastSurfer GPU with fMRIPrep reuse.")
    p.add_argument("command", choices=["doctor", "plan", "fastsurfer", "fmriprep", "all"])
    p.add_argument("--subject", default="sub-YZ1")
    p.add_argument("--fs-subject", default=None, help="FastSurfer/FreeSurfer subjects_dir 内的 subject id；默认等于 --subject。")
    p.add_argument("--session", default="ses-mri0")
    p.add_argument("--input-subject", type=Path, default=SOURCE_TEST_INPUT)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--bids-root", type=Path, default=None, help="复用已有 BIDS 根目录，避免在 FastSurfer 输出目录重复保存 BIDS。")
    p.add_argument("--fastsurfer-subjects-dir", type=Path, default=None, help="FastSurfer/FreeSurfer-compatible SUBJECTS_DIR。默认使用 BIDS derivatives/FASTSURFER。")
    p.add_argument("--fs-license", type=Path, default=DEFAULT_FS_LICENSE)
    p.add_argument("--fastsurfer-image", default=os.environ.get("FASTSURFER_IMAGE", DEFAULT_FASTSURFER_IMAGE))
    p.add_argument("--agent-python", type=Path, default=DEFAULT_AGENT_PYTHON)
    p.add_argument("--fmriprep-runner", type=Path, default=DEFAULT_FMRIPREP_RUNNER)
    p.add_argument("--templateflow", type=Path, default=DEFAULT_TEMPLATEFLOW)
    return p


def main() -> int:
    args = parser().parse_args()
    ctx = build_context(args)
    ctx.output_root.mkdir(parents=True, exist_ok=True)
    if args.command == "doctor":
        checks = docker_gpu_probe(ctx)
        print(json.dumps({"doctor": str(ctx.output_root / "logs" / "doctor.json"), "docker_returncode": checks["docker_images"]["returncode"]}, ensure_ascii=False))
        return 0 if checks["docker_images"]["returncode"] == 0 else 1
    t1_path, _ = prepare_minimal_bids(ctx)
    write_plan(ctx, t1_path)
    if args.command == "plan":
        print(json.dumps({"plan": str(ctx.output_root / "command_plan.json")}, ensure_ascii=False))
        return 0
    if args.command == "fastsurfer":
        return run_fastsurfer(ctx)
    if args.command == "fmriprep":
        return run_fmriprep(ctx)
    if args.command == "all":
        rc = run_fastsurfer(ctx)
        if rc != 0:
            return rc
        return run_fmriprep(ctx)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
