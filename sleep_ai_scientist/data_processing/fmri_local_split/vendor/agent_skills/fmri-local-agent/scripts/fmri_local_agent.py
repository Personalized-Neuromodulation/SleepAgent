#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import concurrent.futures
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PIPELINE = ROOT / "agent_skills" / "fmri-pipeline" / "scripts" / "fmri_pipeline.py"
FASTSURFER_PIPELINE = ROOT / "agent_skills" / "fmri-fastsurfer-fmriprep" / "scripts" / "run_fastsurfer_fmriprep.py"
DEFAULT_INPUT_ROOT = Path(os.environ.get("FMRI_INPUT_ROOT", "/data/input"))
OUTPUT_DATASET_NAME = "multimodal_sleep_data"
LEGACY_ANALYSIS_DIR_NAMES = {"analysis_fast", "analysis_free", "fmri_fast", "fmri_free"}
DEFAULT_FREE_OUTPUT_ROOT = Path(os.environ.get("FMRI_FREE_OUTPUT_ROOT", f"/outputs/{OUTPUT_DATASET_NAME}"))
DEFAULT_FAST_OUTPUT_ROOT = Path(os.environ.get("FMRI_FAST_OUTPUT_ROOT", f"/outputs/{OUTPUT_DATASET_NAME}"))
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:latest")
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_FS_LICENSE = Path(os.environ.get("FS_LICENSE", ROOT / "tools" / "license.txt"))
DEFAULT_ERROR_MIRROR_AGENT_DIR = os.environ.get("FMRI_ERROR_MIRROR_AGENT_DIR", "").strip()
LOCAL_AGENT_PYTHON = Path("/opt/anaconda3/envs/agent/bin/python")
DEFAULT_PYTHON = Path(os.environ.get("FMRI_AGENT_PYTHON", str(LOCAL_AGENT_PYTHON if LOCAL_AGENT_PYTHON.exists() else "python")))
DEFAULT_CPU_CORES = 24
DEFAULT_GPU_MEMORY_GB = 8
MNI_TEMPLATE_SPACES = {
    "both": "T1w MNI152NLin6Asym:res-2 MNI152NLin2009cAsym:res-2 fsnative fsaverage",
    "6": "T1w MNI152NLin6Asym:res-2 fsnative fsaverage",
    "2009": "T1w MNI152NLin2009cAsym:res-2 fsnative fsaverage",
}
SKILL_TO_PIPELINE_COMMAND = {
    "fmri-bids-ingest": "bids",
    "fmri-fmriprep-qc": "fmriprep",
    "fmri-denoise-regressors": "denoise",
    "fmri-surface-segment": "segment",
    "fmri-timefreq-stats": "timefreq",
    "fmri-pipeline": "full",
}
FULL_SKILL_ORDER = [
    "fmri-bids-ingest",
    "fmri-fmriprep-qc",
    "fmri-denoise-regressors",
    "fmri-surface-segment",
    "fmri-timefreq-stats",
]
START_TIME = time.monotonic()


def elapsed() -> str:
    seconds = int(time.monotonic() - START_TIME)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def log_step(message: str) -> None:
    print(f"[{elapsed()}] {message}", flush=True)


def log_subject(subject: str, message: str) -> None:
    print(f"[{elapsed()}] [{subject}] {message}", flush=True)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def current_agent_log_dir(output_root: Path) -> Path:
    configured = os.environ.get("FMRI_AGENT_LOG_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return output_root / "agent_log" / "adhoc"


def init_agent_log_dir(output_root: Path) -> Path:
    configured = os.environ.get("FMRI_AGENT_LOG_DIR", "").strip()
    if configured:
        log_dir = Path(configured).expanduser()
    else:
        run_id = os.environ.get("FMRI_AGENT_RUN_ID", "").strip() or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_dir = output_root / "agent_log" / run_id
        os.environ["FMRI_AGENT_LOG_DIR"] = str(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def agent_path(args: argparse.Namespace, *parts: str) -> Path:
    log_dir = getattr(args, "agent_log_dir", None) or current_agent_log_dir(args.output_root)
    return Path(log_dir).joinpath(*parts)


def bids_root(args: argparse.Namespace) -> Path:
    return args.output_root / "bids"


def append_error(output_root: Path, message: str) -> None:
    line = f"[{elapsed()}] {message}"
    primary = current_agent_log_dir(output_root) / "error.txt"
    append_text(primary, line)
    mirror = Path(DEFAULT_ERROR_MIRROR_AGENT_DIR).expanduser() / "error.txt" if DEFAULT_ERROR_MIRROR_AGENT_DIR else primary
    if mirror != primary:
        append_text(mirror, line)


def command_label(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def run_capture(cmd: list[str], timeout: int = 30) -> dict:
    result = {"cmd": cmd, "returncode": None, "stdout": "", "stderr": "", "error": ""}
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        result.update({"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def http_json(host: str, endpoint: str, payload: dict | None = None, timeout: int = 30) -> tuple[int | None, object | None, str]:
    url = host.rstrip("/") + endpoint
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body) if body else None, ""
    except urllib.error.HTTPError as exc:
        return exc.code, None, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


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
    if (subject_root / "mri").is_dir() and any((subject_root / "mri").rglob("*.dcm")):
        return True
    return False


def child_dirs(path: Path) -> list[Path]:
    return sorted(child for child in path.iterdir() if child.is_dir()) if path.exists() else []


def looks_like_subject_dir(path: Path) -> bool:
    return path.is_dir() and path.name.startswith("sub-")


def has_subject_children(path: Path) -> bool:
    return any(looks_like_subject_dir(child) for child in child_dirs(path))


def discover_experiment_dirs(input_root: Path) -> list[Path]:
    if not input_root.exists() or not input_root.is_dir():
        return []
    if has_subject_children(input_root):
        return [input_root]
    experiments = [child for child in child_dirs(input_root) if has_subject_children(child)]
    return experiments


def filter_experiments_from_prompt(experiments: list[Path], prompt_parse: dict | None, task_text: str = "") -> list[Path]:
    requested = (prompt_parse or {}).get("experiments")
    if not isinstance(requested, list):
        requested = []
    if not requested and task_text:
        lowered_task = task_text.casefold()
        requested = [exp.name for exp in experiments if exp.name.casefold() in lowered_task]
    if not requested:
        return experiments
    by_name = {exp.name: exp for exp in experiments}
    by_lower = {exp.name.casefold(): exp for exp in experiments}
    selected = []
    for name in requested:
        text = clean_llm_string(name)
        candidate = by_name.get(text) or by_lower.get(text.casefold())
        if candidate is None:
            candidate = next((exp for exp in experiments if str(exp) == text or exp.name.casefold() in text.casefold()), None)
        if candidate is not None and candidate not in selected:
            selected.append(candidate)
    return selected or experiments


def experiment_name_for(input_root: Path) -> str:
    return input_root.name


def discover_input(input_root: Path) -> dict:
    if not input_root.exists():
        return {"input_root": str(input_root), "subjects": [], "exists": False, "error": f"输入根目录不存在：{input_root}"}
    subjects = sorted(path for path in input_root.iterdir() if path.is_dir() and not path.name.startswith("."))
    summary = {"input_root": str(input_root), "subjects": [], "exists": True}
    for subject in subjects:
        sessions = find_session_dirs(subject)
        anat_series = sorted(path for ses in sessions for path in child_dirs(ses / "anat"))
        func_series = sorted(path for ses in sessions for path in child_dirs(ses / "func"))
        summary["subjects"].append(
            {
                "subject": subject.name,
                "bids_subject": bids_subject_id(subject.name),
                "has_imaging_data": subject_has_imaging_data(subject),
                "session_count": len(sessions),
                "sessions": [str(path.relative_to(subject)) for path in sessions],
                "anat_series_count": len(anat_series),
                "func_series_count": len(func_series),
                "anat_nifti_count": sum(len(list(ses.glob("anat/**/*.nii"))) + len(list(ses.glob("anat/**/*.nii.gz"))) for ses in sessions),
                "func_nifti_count": sum(len(list(ses.glob("func/**/*.nii"))) + len(list(ses.glob("func/**/*.nii.gz"))) for ses in sessions),
                "func_dicom_count": sum(len(list(ses.glob("func/**/*.dcm"))) for ses in sessions),
                "anat_series": [path.name for path in anat_series],
                "func_series": [path.name for path in func_series],
            }
        )
    return summary


def available_subjects(input_root: Path) -> list[str]:
    subjects = sorted(path for path in input_root.iterdir() if path.is_dir() and not path.name.startswith("."))
    with_data = [path.name for path in subjects if subject_has_imaging_data(path)]
    return with_data or [path.name for path in subjects]


def bids_subject_id(subject_folder: str) -> str:
    return subject_folder if subject_folder.startswith("sub-") else f"sub-{subject_folder}"


def expected_freesurfer_subject_id(bids_root: Path, bids_subject: str) -> str:
    override = os.environ.get("FMRI_FS_SUBJECT_ID", "").strip()
    if override:
        return override
    subject_root = bids_root / bids_subject
    sessions = sorted(path.name for path in subject_root.glob("ses-*") if path.is_dir())
    if len(sessions) == 1:
        return f"{bids_subject}_{sessions[0]}"
    return bids_subject


def subject_aliases(subject_folder: str) -> set[str]:
    bids = bids_subject_id(subject_folder)
    raw = subject_folder.removeprefix("sub-")
    return {subject_folder, bids, raw}


def subjects_from_task(task_text: str, input_root: Path) -> list[str]:
    requested = []
    subjects = available_subjects(input_root)
    for subject in subjects:
        aliases = sorted(subject_aliases(subject), key=len, reverse=True)
        if any(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(alias)}(?![A-Za-z0-9_-])", task_text) for alias in aliases):
            requested.append(subject)
    for match in re.findall(r"sub-[A-Za-z0-9_-]+", task_text):
        for subject in subjects:
            if match in subject_aliases(subject) and subject not in requested:
                requested.append(subject)
    return requested


def subjects_from_prompt_parse(prompt_parse: dict | None, input_root: Path) -> list[str]:
    parsed_subjects = (prompt_parse or {}).get("subjects")
    if not isinstance(parsed_subjects, list) or not parsed_subjects:
        return []
    requested = []
    subjects = available_subjects(input_root)
    for parsed in parsed_subjects:
        parsed_text = clean_llm_string(parsed)
        if not parsed_text:
            continue
        for subject in subjects:
            if parsed_text in subject_aliases(subject) and subject not in requested:
                requested.append(subject)
                break
    return requested


def normalize_single_subject_input_root(input_root: Path, prompt_parse: dict | None) -> tuple[Path, dict | None, str]:
    if not looks_like_subject_dir(input_root) or not subject_has_imaging_data(input_root):
        return input_root, prompt_parse, ""
    updated = dict(prompt_parse or {})
    parsed_subjects = updated.get("subjects")
    subject = input_root.name
    if not isinstance(parsed_subjects, list) or not any(str(item) in subject_aliases(subject) for item in parsed_subjects):
        updated["subjects"] = [subject]
    return input_root.parent, updated, subject


def confirm_all_subjects(subjects: list[str], assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        log_step("agent: 未指定被试且当前不是交互终端；为避免误跑所有被试，请加 --yes 确认。")
        return False
    print("未在任务中指定被试。默认将分析 test_data 下所有被试：", flush=True)
    for subject in subjects:
        print(f"  - {subject}", flush=True)
    answer = input("确认分析所有被试？输入 yes 确认：").strip().lower()
    return answer in {"yes", "y"}


def choose_surface_mode(args: argparse.Namespace, task_text: str) -> str:
    if args.surface_mode in {"0", "1"}:
        return args.surface_mode
    lowered = task_text.lower()
    if "fastsurfer" in lowered or "fast surfer" in lowered:
        return "1"
    if not sys.stdin.isatty():
        log_step("agent: 未交互选择 surface 模式，默认使用 0=FreeSurfer/fMRIPrep。")
        return "0"
    print("请选择 surface reconstruction 路径：", flush=True)
    print("  0: FreeSurfer/fMRIPrep 默认路径", flush=True)
    print("  1: FastSurfer 预跑，再由 fMRIPrep 复用 FastSurfer subjects_dir", flush=True)
    answer = input("请输入 0 或 1 [默认 0]：").strip()
    return "1" if answer == "1" else "0"


def default_output_root_for_surface(surface_mode: str) -> Path:
    return DEFAULT_FAST_OUTPUT_ROOT if surface_mode == "1" else DEFAULT_FREE_OUTPUT_ROOT


def analysis_dir_name(surface_mode: str) -> str:
    return OUTPUT_DATASET_NAME


def should_nest_output_for_experiment(input_root: Path) -> bool:
    return False


def output_root_for_experiment(resolved_output_root: Path, experiment: Path, surface_mode: str) -> Path:
    return resolved_output_root


def infer_surface_mode(args: argparse.Namespace, task_text: str) -> str:
    if args.surface_mode in {"0", "1"}:
        return args.surface_mode
    lowered = task_text.lower()
    return "1" if "fastsurfer" in lowered or "fast surfer" in lowered else "0"


def choose_mni_template(args: argparse.Namespace, task_text: str) -> str:
    if os.environ.get("FMRIPREP_OUTPUT_SPACES"):
        log_step("agent: 检测到 FMRIPREP_OUTPUT_SPACES，使用用户环境变量中的 output spaces。")
        return "env"
    if args.mni_template in MNI_TEMPLATE_SPACES:
        return args.mni_template
    lowered = task_text.lower()
    if "mni152nlin6asym" in lowered and "mni152nlin2009c" not in lowered:
        return "6"
    if "mni152nlin2009c" in lowered and "mni152nlin6asym" not in lowered:
        return "2009"
    if not sys.stdin.isatty():
        log_step("agent: 未交互选择 MNI 模板，默认使用两个模板 MNI152NLin6Asym 和 MNI152NLin2009cAsym。")
        return "both"
    print("请选择 fMRIPrep MNI 输出模板：", flush=True)
    print("  0: 两个模板 MNI152NLin6Asym + MNI152NLin2009cAsym [默认]", flush=True)
    print("  1: 仅 MNI152NLin6Asym", flush=True)
    print("  2: 仅 MNI152NLin2009cAsym", flush=True)
    answer = input("请输入 0、1 或 2 [默认 0]：").strip()
    if answer == "1":
        return "6"
    if answer == "2":
        return "2009"
    return "both"


def resolve_run_subjects(args: argparse.Namespace, task_text: str) -> list[str]:
    all_subjects = available_subjects(args.input_root)
    requested = subjects_from_task(task_text, args.input_root)
    if requested:
        log_step(f"agent: 根据任务选择被试 {requested}")
        return requested
    if not all_subjects:
        raise FileNotFoundError(f"没有在 {args.input_root} 下找到被试目录")
    if not confirm_all_subjects(all_subjects, args.yes):
        raise RuntimeError("用户未确认分析所有被试，已停止。")
    log_step(f"agent: 用户确认分析所有被试 {all_subjects}")
    return all_subjects


def parse_run_subjects(args: argparse.Namespace, task_text: str) -> list[str]:
    all_subjects = available_subjects(args.input_root)
    requested = subjects_from_task(task_text, args.input_root)
    if requested:
        log_step(f"agent: 根据任务选择被试 {requested}")
        return requested
    if not all_subjects:
        raise FileNotFoundError(f"没有在 {args.input_root} 下找到被试目录")
    log_step(f"agent: 任务未指定被试，解析为所有被试 {all_subjects}")
    return all_subjects


def load_skill_context() -> str:
    names = [
        "fmri-pipeline",
        "fmri-bids-ingest",
        "fmri-fmriprep-qc",
        "fmri-denoise-regressors",
        "fmri-surface-segment",
        "fmri-timefreq-stats",
    ]
    chunks = []
    for name in names:
        path = ROOT / "agent_skills" / name / "SKILL.md"
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            chunks.append(f"## {name}\n{text[:1800]}")
    return "\n\n".join(chunks)


def ollama_generate(host: str, model: str, prompt: str, timeout: int = 120) -> tuple[str, dict]:
    payload = {"model": model, "prompt": prompt, "stream": False}
    status, body, error = http_json(host, "/api/generate", payload, timeout=timeout)
    meta = {"status": status, "error": error}
    if isinstance(body, dict):
        meta.update({k: body.get(k) for k in ["model", "done", "total_duration", "load_duration"]})
        return str(body.get("response", "")), meta
    return "", meta


def extract_json_object(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def clean_llm_string(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "null", "none", "未指定", "不指定"} else text


def path_from_llm(value: object) -> Path | None:
    text = clean_llm_string(value)
    if not text:
        return None
    return Path(text).expanduser()


def absolute_paths_from_text(text: str) -> list[str]:
    paths: list[str] = []
    for match in re.finditer(r"/[^\s，,。；;：:]+", text or ""):
        value = match.group(0)
        for marker in ["输出目录", "输出", "输入目录", "输入", "下的", "里的", "中的", "被试", "数据"]:
            index = value.find(marker)
            if index > 0:
                value = value[:index]
        value = value.rstrip("\"'）)]}、")
        if value and value not in paths:
            paths.append(value)
    return paths


def fallback_paths_from_task(task_text: str) -> tuple[str, str]:
    paths = absolute_paths_from_text(task_text)
    input_root = ""
    output_root = ""
    for path in paths:
        before = task_text[: task_text.find(path)] if path in task_text else ""
        context = before[-12:]
        if any(token in context.lower() for token in ["input", "输入", "数据"]):
            input_root = input_root or path
        elif any(token in context.lower() for token in ["output", "输出", "结果"]):
            output_root = output_root or path
    if not input_root and paths:
        input_root = paths[0]
    if not output_root and len(paths) > 1:
        output_root = paths[1]
    return input_root, output_root


def normalize_prompt_parse(payload: dict | None, task_text: str) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    fallback_input, fallback_output = fallback_paths_from_task(task_text)
    parsed = {
        "main_task": clean_llm_string(payload.get("main_task")) or task_text,
        "input_root": clean_llm_string(payload.get("input_root") or payload.get("input_dir") or payload.get("data_dir")) or fallback_input,
        "output_root": clean_llm_string(payload.get("output_root") or payload.get("output_dir") or payload.get("result_dir")) or fallback_output,
        "experiments": [],
        "subjects": [],
        "surface_mode": clean_llm_string(payload.get("surface_mode")),
        "mni_template": clean_llm_string(payload.get("mni_template")),
    }
    experiments = payload.get("experiments") or payload.get("experiment_names") or payload.get("projects")
    if isinstance(experiments, list):
        parsed["experiments"] = [clean_llm_string(item) for item in experiments if clean_llm_string(item)]
    elif clean_llm_string(experiments):
        parsed["experiments"] = [clean_llm_string(experiments)]
    subjects = payload.get("subjects")
    if isinstance(subjects, list):
        parsed["subjects"] = [clean_llm_string(item) for item in subjects if clean_llm_string(item)]
    elif clean_llm_string(subjects):
        parsed["subjects"] = [clean_llm_string(subjects)]
    if parsed["surface_mode"].lower() in {"fastsurfer", "fast", "1"}:
        parsed["surface_mode"] = "1"
    elif parsed["surface_mode"].lower() in {"freesurfer", "free", "0"}:
        parsed["surface_mode"] = "0"
    if parsed["mni_template"].lower() in {"both", "all", "两个", "全部"}:
        parsed["mni_template"] = "both"
    elif "2009" in parsed["mni_template"].lower():
        parsed["mni_template"] = "2009"
    elif "6" in parsed["mni_template"].lower():
        parsed["mni_template"] = "6"
    return parsed


def parse_user_prompt(args: argparse.Namespace, command: str, task_text: str) -> dict:
    if command not in {"run", "analyze", "plan", "doctor"}:
        return normalize_prompt_parse(None, task_text)
    prompt = (
        "你是命令行参数解析器。请从用户中文/英文自然语言中抽取 fMRI 分析任务和路径，"
        "只输出 JSON，不要 Markdown，不要解释。JSON schema:\n"
        "{\n"
        '  "main_task": "用户真正要执行的任务；去掉纯路径说明但保留分析要求",\n'
        '  "input_root": "待分析原始数据根目录；没有则空字符串",\n'
        '  "output_root": "分析结果输出根目录；没有则空字符串",\n'
        '  "experiments": ["用户点名的实验/项目目录名，如 JingZongOLT、YangZhiHC；没有则空数组"],\n'
        '  "subjects": ["用户点名的被试，如 sub-ISM035；没有则空数组"],\n'
        '  "surface_mode": "0|1|空字符串；0=FreeSurfer/fMRIPrep, 1=FastSurfer",\n'
        '  "mni_template": "both|6|2009|空字符串"\n'
        "}\n\n"
        "路径通常以 / 开头，也可能跟在 输入、input、数据、输出、output、结果 等词后面。"
        "不要把不存在的默认目录编造为用户输入。"
        "如果用户没有明确输入目录或输出目录，对应字段必须为空字符串。\n\n"
        f"原始用户输入:\n{task_text}\n"
    )
    response = ""
    meta = {"skipped": True}
    payload = None
    response, meta = ollama_generate(args.ollama_host, args.model, prompt, timeout=min(args.ollama_timeout, 60))
    payload = extract_json_object(response)
    parsed = normalize_prompt_parse(payload, task_text)
    parsed["model"] = args.model
    parsed["model_meta"] = meta
    parsed["raw_llm_response"] = response
    return parsed


def default_task_text() -> str:
    if sys.stdin.isatty():
        log_step("请输入主要任务，例如：分析默认目录下的 fMRI 数据")
        return input("> ").strip()
    return "分析默认目录下的 fMRI 数据，完成 BIDS 整理、fMRIPrep、去噪、分段、时频和 QC。"


def prompt_task_text(current_task: str = "") -> str:
    if current_task:
        print(f"当前任务：{current_task}", flush=True)
    while True:
        answer = input("请输入新的主要任务：").strip()
        if answer:
            return answer
        print("任务不能为空。", flush=True)


def confirmed(answer: str) -> bool:
    return answer.strip().lower() in {"yes", "y", "是", "同意", "确认", "继续", "ok", "1"}


def declined(answer: str) -> bool:
    return answer.strip().lower() in {"no", "n", "否", "不同意", "取消", "返回", "重新输入", "0"}


def confirm_parsed_command(args: argparse.Namespace, orchestration: dict, task_text: str) -> bool:
    if args.yes:
        return True
    if not sys.stdin.isatty():
        log_step("agent: 当前不是交互终端；解析后确认需要交互输入。请加 --yes 明确确认后再运行。")
        return False

    steps = orchestration.get("steps", [])
    print("\n已解析用户命令，请确认是否继续执行：", flush=True)
    print(f"  任务: {task_text}", flush=True)
    print(f"  输入目录: {args.input_root}", flush=True)
    print(f"  输出目录: {args.output_root}", flush=True)
    print(f"  被试: {', '.join(orchestration.get('subjects', [])) or '未解析'}", flush=True)
    print(f"  Surface 路径: {orchestration.get('surface_mode', '未解析')} (0=FreeSurfer/fMRIPrep, 1=FastSurfer)", flush=True)
    print(f"  MNI 模板: {orchestration.get('mni_template', '未解析')}", flush=True)
    print("  执行步骤:", flush=True)
    for index, step in enumerate(steps, start=1):
        skill = step.get("skill", "")
        action = step.get("action", "")
        reason = step.get("reason", "")
        print(f"    {index}. {skill}/{action} - {reason}", flush=True)
    while True:
        answer = input("同意继续执行？输入 yes 继续，no 返回重新输入：").strip()
        if confirmed(answer):
            return True
        if declined(answer):
            return False
        print("请输入 yes 或 no。", flush=True)


def normalize_analysis_output_root(path: Path, surface_mode: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.name == "fmri_result":
        return resolved.parent / OUTPUT_DATASET_NAME
    if resolved.name in LEGACY_ANALYSIS_DIR_NAMES:
        return resolved.parent / OUTPUT_DATASET_NAME
    return resolved


def resolve_output_root(args: argparse.Namespace, command: str, task_text: str = "", prompt_parse: dict | None = None) -> Path:
    surface_mode = infer_surface_mode(args, task_text)
    if args.output_root is not None:
        return normalize_analysis_output_root(args.output_root, surface_mode)
    parsed_output = path_from_llm((prompt_parse or {}).get("output_root"))
    if parsed_output is not None:
        return normalize_analysis_output_root(parsed_output, surface_mode)
    env_output = os.environ.get("FMRI_OUTPUT_ROOT", "").strip()
    if env_output:
        return normalize_analysis_output_root(Path(env_output), surface_mode)
    default_root = default_output_root_for_surface(surface_mode)
    if command in {"run", "analyze", "plan"} and sys.stdin.isatty():
        print("请输入最终分析结果父目录或 analysis 目录：", flush=True)
        print(f"  默认: {default_root}", flush=True)
        print(f"  若输入父目录，将自动使用子目录 {analysis_dir_name(surface_mode)}", flush=True)
        answer = input("输出目录 [直接回车使用默认]：").strip()
        if answer:
            return normalize_analysis_output_root(Path(answer), surface_mode)
    log_step(f"agent: 未指定输出目录，使用默认 analysis 目录 {default_root}")
    return default_root


def resolve_input_root(args: argparse.Namespace, command: str, prompt_parse: dict | None = None) -> Path:
    parsed_input = path_from_llm((prompt_parse or {}).get("input_root"))
    configured = args.input_root or parsed_input or Path(os.environ.get("FMRI_INPUT_ROOT", DEFAULT_INPUT_ROOT))
    root = configured.expanduser().resolve()
    if (args.input_root is not None or parsed_input is not None) and root.exists():
        return root
    if args.input_root is None and parsed_input is None and command in {"run", "analyze", "plan", "doctor"} and sys.stdin.isatty():
        print("请输入待分析 fMRI 数据根目录 input：", flush=True)
        if root.exists():
            print(f"  默认: {root}", flush=True)
        else:
            print(f"  当前默认不存在: {root}", flush=True)
        print("  目录下应包含 sub-* 或 YZ* 等被试文件夹。", flush=True)
        while True:
            answer = input("输入目录 [直接回车使用默认]：").strip()
            if not answer:
                if root.exists() and root.is_dir():
                    return root
                continue
            candidate = Path(answer).expanduser().resolve()
            if candidate.exists() and candidate.is_dir():
                return candidate
            print(f"目录不存在或不是文件夹：{candidate}", flush=True)
    if parsed_input is not None and command in {"run", "analyze", "plan", "doctor"} and sys.stdin.isatty():
        print(f"LLM 解析到的输入目录不存在或不是文件夹：{root}", flush=True)
        while True:
            answer = input("请重新输入待分析 fMRI 数据根目录：").strip()
            if not answer:
                continue
            candidate = Path(answer).expanduser().resolve()
            if candidate.exists() and candidate.is_dir():
                return candidate
            print(f"目录不存在或不是文件夹：{candidate}", flush=True)
    env_input = os.environ.get("FMRI_INPUT_ROOT", "").strip()
    if env_input and Path(env_input).expanduser().exists():
        return Path(env_input).expanduser().resolve()
    if command in {"run", "analyze", "plan", "doctor"} and sys.stdin.isatty():
        print("请输入待分析 fMRI 数据根目录 input：", flush=True)
        print(f"  当前默认不存在: {root}", flush=True)
        print("  目录下应包含 sub-* 或 YZ* 等被试文件夹。", flush=True)
        while True:
            answer = input("输入目录：").strip()
            if not answer:
                continue
            candidate = Path(answer).expanduser().resolve()
            if candidate.exists() and candidate.is_dir():
                return candidate
            print(f"目录不存在或不是文件夹：{candidate}", flush=True)
    return root


def resolve_fs_license(args: argparse.Namespace, command: str) -> Path:
    license_path = args.fs_license.expanduser().resolve()
    if license_path.exists() and license_path.is_file():
        return license_path
    if command in {"run", "analyze", "plan", "doctor"} and sys.stdin.isatty():
        print("未找到 FreeSurfer license.txt：", flush=True)
        print(f"  当前路径: {license_path}", flush=True)
        print("  fMRIPrep/FreeSurfer 需要该文件才能运行 surface reconstruction。", flush=True)
        while True:
            answer = input("请输入 license.txt 文件路径：").strip()
            if not answer:
                continue
            candidate = Path(answer).expanduser().resolve()
            if candidate.exists() and candidate.is_file():
                return candidate
            print(f"文件不存在或不是普通文件：{candidate}", flush=True)
    return license_path


def doctor(args: argparse.Namespace) -> dict:
    log_step("doctor: 检查输入数据、Ollama 服务和模型加载状态")
    model = args.model
    host = args.ollama_host
    input_summary = discover_input(args.input_root)
    subject_count = len(input_summary.get("subjects", []))
    log_step(f"doctor: 发现 {subject_count} 个被试，输入根目录 {args.input_root}")
    ollama_path = shutil.which("ollama")
    log_step(f"doctor: ollama binary = {ollama_path or 'NOT FOUND'}")
    tags_status, tags_body, tags_error = http_json(host, "/api/tags", timeout=10)
    models = []
    if isinstance(tags_body, dict):
        models = [item.get("name", "") for item in tags_body.get("models", [])]
    log_step(f"doctor: Ollama tags status={tags_status}, models={models}")
    generate_text, generate_meta = ("", {"skipped": True})
    if model in models:
        log_step(f"doctor: probing model {model}")
        generate_text, generate_meta = ollama_generate(host, model, "只回复 OK。", timeout=60)
    result = {
        "ollama_binary": ollama_path,
        "ollama_cli_version": run_capture(["ollama", "--version"]) if ollama_path else {"error": "ollama not found"},
        "ollama_host": host,
        "ollama_tags_status": tags_status,
        "ollama_tags_error": tags_error,
        "available_models": models,
        "requested_model": model,
        "model_available": model in models,
        "model_probe": generate_meta,
        "model_probe_response": generate_text[:200],
        "input": input_summary,
        "pipeline": str(PIPELINE),
        "pipeline_exists": PIPELINE.exists(),
    }
    write_json(agent_path(args, "doctor.json"), result)
    log_step(f"doctor: 写入 {agent_path(args, 'doctor.json')}")
    return result


def build_plan(args: argparse.Namespace, status: dict, task_text: str = "") -> dict:
    log_step("plan: 读取 skill 摘要并构造本地模型提示")
    prompt = (
        "你是本地 fMRI 数据分析 agent。根据以下 skill 摘要和输入数据状态，"
        "输出简洁的中文分析计划。必须调用已有 fmri-pipeline analyze，"
        "缺失依赖时只记录状态，不伪造医学影像结果。\n\n"
        f"用户主要任务:\n{task_text or '分析默认目录下的 fMRI 数据'}\n\n"
        f"输入状态:\n{json.dumps(status.get('input', {}), ensure_ascii=False, indent=2)}\n\n"
        f"Skill 摘要:\n{load_skill_context()}"
    )
    response = ""
    meta = {"skipped": True}
    if status.get("model_available"):
        log_step(f"plan: 调用 Ollama 模型 {args.model} 生成分析计划")
        response, meta = ollama_generate(args.ollama_host, args.model, prompt, timeout=args.ollama_timeout)
        log_step("plan: 本地模型计划生成完成")
    else:
        log_step(f"plan: 模型不可用，跳过 LLM 计划生成: {args.model}")
    plan = {
        "model": args.model,
        "task": task_text,
        "model_meta": meta,
        "llm_plan": response,
        "pipeline_command": [
            str(args.python if args.python.exists() else Path(sys.executable)),
            str(PIPELINE),
            "analyze",
        ],
        "environment": {
            "FMRI_INPUT_ROOT": str(args.input_root),
            "FMRI_OUTPUT_ROOT": str(bids_root(args)),
            "OLLAMA_MODEL": args.model,
        },
    }
    write_json(agent_path(args, "plan.json"), plan)
    log_step(f"plan: 写入 {agent_path(args, 'plan.json')}")
    return plan


def run_streaming_command(cmd: list[str], log_path: Path, env: dict[str, str], label: str = "") -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"{label}: " if label else ""
    log_step(prefix + "exec: command = " + command_label(cmd))
    start = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        log.write("COMMAND:\n" + command_label(cmd) + "\n\nOUTPUT:\n")
        log.flush()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            if label:
                print(f"[{elapsed()}] [{label}] {line}", end="", flush=True)
            else:
                print(line, end="", flush=True)
            log.write(line)
            log.flush()
        returncode = proc.wait()
        duration = int(time.monotonic() - start)
        log.write(f"\n\nRETURN_CODE: {returncode}\nDURATION_SECONDS: {duration}\n")
    log_step(prefix + f"exec: 完成 returncode={returncode}, elapsed_seconds={duration}")
    return int(returncode)


def analysis_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    path_entries = ["/opt/fsl/bin", "/home/zyb/fsl/bin", "/home/zyb/fsl/pkgs/dcm2niix-1.0.20250506-hb700be7_1/bin", env.get("PATH", "")]
    env.update(
        {
            "PATH": os.pathsep.join(entry for entry in path_entries if entry),
            "FMRI_INPUT_ROOT": str(args.input_root),
            "FMRI_OUTPUT_ROOT": str(bids_root(args)),
            "FMRI_DERIVATIVES_ROOT": str(bids_root(args) / "derivatives" / "FMRIPREP"),
            "FMRI_AGENT_LOG_DIR": str(agent_path(args)),
            "FS_LICENSE": str(args.fs_license),
            "FREESURFER_HOME": env.get("FREESURFER_HOME", "/usr/local/freesurfer/8.1.0"),
            "FREESURFER": env.get("FREESURFER", env.get("FREESURFER_HOME", "/usr/local/freesurfer/8.1.0")),
            "OLLAMA_MODEL": args.model,
        }
    )
    env.setdefault("FMRIPREP_WORK_DIR", str(bids_root(args) / "derivatives" / "work"))
    return env


def subject_jobs(args: argparse.Namespace, surface_mode: str, subject_count: int) -> int:
    requested = args.subject_jobs
    env_requested = os.environ.get("FMRI_SUBJECT_JOBS")
    if requested is None and env_requested:
        try:
            requested = int(env_requested)
        except ValueError:
            requested = None
    if requested is not None:
        jobs = max(1, requested)
    elif surface_mode == "1":
        jobs = 1
    else:
        jobs = max(1, min(subject_count, DEFAULT_CPU_CORES // 12 or 1))
    if surface_mode == "1" and requested is None:
        jobs = 1
    return max(1, min(jobs, subject_count))


def per_subject_threads(args: argparse.Namespace, surface_mode: str, jobs: int) -> tuple[str, str]:
    if os.environ.get("FMRIPREP_NTHREADS") or os.environ.get("FMRIPREP_OMP_NTHREADS"):
        return os.environ.get("FMRIPREP_NTHREADS", "8"), os.environ.get("FMRIPREP_OMP_NTHREADS", "2")
    if surface_mode == "1":
        return "16", "4"
    nthreads = max(4, DEFAULT_CPU_CORES // max(1, jobs))
    omp = max(1, min(2, nthreads // 4))
    return str(nthreads), str(omp)


def subject_env(args: argparse.Namespace, subject: str, surface_mode: str, jobs: int = 1) -> dict[str, str]:
    env = analysis_env(args)
    env["FMRI_SUBJECT"] = subject
    env["FMRI_SURFACE_MODE"] = surface_mode
    nthreads, omp = per_subject_threads(args, surface_mode, jobs)
    env.setdefault("FMRIPREP_NTHREADS", nthreads)
    env.setdefault("FMRIPREP_OMP_NTHREADS", omp)
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS", "1")
    mni_template = getattr(args, "resolved_mni_template", None)
    if mni_template in MNI_TEMPLATE_SPACES:
        env.setdefault("FMRIPREP_OUTPUT_SPACES", MNI_TEMPLATE_SPACES[mni_template])
    if surface_mode == "0":
        fs_subjects_root = os.environ.get("FMRI_FS_SUBJECTS_DIR", "").strip()
        if not fs_subjects_root:
            fs_subjects_root = str(bids_root(args) / "derivatives" / "FREESURFER")
        env.setdefault("FMRI_FS_SUBJECTS_DIR", fs_subjects_root)
        env.setdefault("FMRI_SURFACE_RECON_BACKEND", "freesurfer")
    else:
        env.setdefault("FMRI_SURFACE_RECON_BACKEND", "fastsurfer")
        env.setdefault("FMRIPREP_FS_NO_RECONALL", "1")
    return env


def subject_work_dir(args: argparse.Namespace, subject: str) -> Path:
    configured = os.environ.get("FMRIPREP_WORK_DIR", "").strip()
    if configured:
        return Path(configured).expanduser() / subject
    return bids_root(args) / "derivatives" / "work" / subject


def cleanup_work_after_success(args: argparse.Namespace, subject: str) -> dict[str, object]:
    work_dir = subject_work_dir(args, subject)
    status: dict[str, object] = {
        "subject": subject,
        "work_dir": str(work_dir),
        "enabled": os.environ.get("FMRI_CLEAN_WORK_ON_SUCCESS", "1") != "0",
        "removed": False,
        "reason": "",
    }
    if not status["enabled"]:
        status["reason"] = "FMRI_CLEAN_WORK_ON_SUCCESS=0，保留 work 目录。"
        return status
    if not work_dir.exists():
        status["reason"] = "work 目录不存在，无需清理。"
        return status
    try:
        shutil.rmtree(work_dir)
    except OSError as exc:
        status["reason"] = f"删除 work 目录失败: {type(exc).__name__}: {exc}"
        append_error(args.output_root, f"subject={subject} cleanup_work_failed path={work_dir} error={status['reason']}")
        return status
    status["removed"] = True
    status["reason"] = "被试完整成功后已删除对应 work 目录。"
    log_subject(subject, f"已清理 work 目录 {work_dir}")
    return status


def attach_success_cleanup(args: argparse.Namespace, result: dict) -> dict:
    subject = str(result.get("subject", ""))
    if subject and int(result.get("returncode", 1)) == 0:
        result["work_cleanup"] = cleanup_work_after_success(args, subject)
    return result


def run_analysis(args: argparse.Namespace, plan: dict) -> int:
    log_step("analyze: 启动 fMRI pipeline analyze")
    python = args.python if args.python.exists() else Path(sys.executable)
    cmd = [str(python), str(PIPELINE), "analyze"]
    log_path = agent_path(args, "pipeline_analyze.log")
    returncode = run_streaming_command(cmd, log_path, analysis_env(args))
    write_json(agent_path(args, "analysis_status.json"), {"returncode": returncode, "log": str(log_path), "plan": plan})
    return int(returncode)


def task_mentions_full_flow(task_text: str) -> bool:
    lowered = task_text.lower()
    return any(token in lowered for token in ["完整", "全流程", "全部流程", "端到端", "完整分析fmri", "full", "complete", "end-to-end"])


def task_stage_skills(task_text: str) -> list[str]:
    lowered = task_text.lower()
    rules = [
        ("fmri-bids-ingest", ["bids", "dicom", "dcm", "转换", "整理", "导入", "ingest"]),
        ("fmri-fmriprep-qc", ["fmriprep", "preprocess", "预处理", "figures", "质控", "qc"]),
        ("fmri-denoise-regressors", ["denoise", "regressor", "regressors", "confounds", "去噪", "回归器", "回归", "混杂"]),
        ("fmri-surface-segment", ["segment", "surface", "surfer_transform", "surface_transform", "sleep_label", "睡眠分期", "分段", "切分"]),
        ("fmri-timefreq-stats", ["time_frequency", "timefreq", "alff", "falff", "psd", "时频", "频域", "统计"]),
    ]
    negation_words = ["不用", "不要", "无需", "不需要", "不进行", "不执行", "跳过", "不跑", "不要跑", "不用跑"]

    def negated(keywords: list[str]) -> bool:
        for keyword in keywords:
            escaped = re.escape(keyword)
            for word in negation_words:
                if re.search(rf"{re.escape(word)}[^，。；,;\n]{{0,16}}{escaped}", lowered):
                    return True
                if re.search(rf"{escaped}[^，。；,;\n]{{0,16}}{re.escape(word)}", lowered):
                    return True
        return False

    negated_skills = {skill for skill, keywords in rules if negated(keywords)}
    selected = [skill for skill, keywords in rules if skill not in negated_skills and any(keyword in lowered for keyword in keywords)]
    if task_mentions_full_flow(task_text) or not selected:
        return [skill for skill in FULL_SKILL_ORDER if skill not in negated_skills]
    ordered = []
    for skill in FULL_SKILL_ORDER:
        if skill in selected:
            ordered.append(skill)
    return ordered


def fallback_orchestration(task_text: str) -> dict:
    steps = [
        {
            "skill": skill,
            "action": "run",
            "reason": "根据用户任务关键词选择该可执行 skill。" if len(task_stage_skills(task_text)) != len(FULL_SKILL_ORDER) else "默认执行完整 fMRI 分析流程。",
        }
        for skill in task_stage_skills(task_text)
    ]
    return {"main_task": task_text, "data_dir": str(DEFAULT_INPUT_ROOT), "steps": steps}


def normalize_orchestration(orchestration: dict | None, task_text: str) -> dict:
    if not isinstance(orchestration, dict):
        return fallback_orchestration(task_text)
    normalized = {"main_task": orchestration.get("main_task", task_text) or task_text, "data_dir": orchestration.get("data_dir", str(DEFAULT_INPUT_ROOT)), "steps": []}
    for step in orchestration.get("steps", []):
        if not isinstance(step, dict):
            continue
        skill = str(step.get("skill", ""))
        action = str(step.get("action", "run"))
        if skill == "fmri-pipeline" and action in {"analyze", "full", "run"}:
            normalized["steps"] = fallback_orchestration(task_text)["steps"]
            return normalized
        if skill in SKILL_TO_PIPELINE_COMMAND and skill != "fmri-pipeline":
            normalized["steps"].append({"skill": skill, "action": "run", "reason": str(step.get("reason", ""))})
    if not normalized["steps"]:
        normalized = fallback_orchestration(task_text)
    return normalized


def build_orchestration(args: argparse.Namespace, status: dict, task_text: str) -> dict:
    log_step("agent: LLM 解析主要任务并编排 skill 顺序")
    prompt = (
        "你是本地 fMRI Agent 的任务编排器。请根据用户主要任务、默认数据目录和可用 skills，"
        "只输出 JSON，不要输出 Markdown。JSON schema:\n"
        "{\n"
        '  "main_task": "string",\n'
        '  "data_dir": "string",\n'
        '  "steps": [{"skill": "fmri-bids-ingest|fmri-fmriprep-qc|fmri-denoise-regressors|fmri-surface-segment|fmri-timefreq-stats", "action": "run", "reason": "string"}]\n'
        "}\n\n"
        "约束：只有用户要求完整分析或没有提出明确局部任务时才选择全部 skill；"
        "否则只选择用户要求的局部 stage。FastSurfer 不是独立 step，由 surface_mode 控制。"
        "真实影像结果必须由实际 pipeline 产生，不能伪造。\n\n"
        f"用户主要任务:\n{task_text}\n\n"
        f"默认待处理数据目录:\n{args.input_root}\n\n"
        f"输入数据状态:\n{json.dumps(status.get('input', {}), ensure_ascii=False, indent=2)}\n\n"
        f"可用 skill 摘要:\n{load_skill_context()}"
    )
    response = ""
    meta = {"skipped": True}
    orchestration = None
    if status.get("model_available"):
        response, meta = ollama_generate(args.ollama_host, args.model, prompt, timeout=args.ollama_timeout)
        orchestration = extract_json_object(response)
    if not orchestration:
        log_step("agent: LLM 未返回可解析 JSON，使用保守默认编排")
        orchestration = fallback_orchestration(task_text)
    else:
        orchestration = normalize_orchestration(orchestration, task_text)
    orchestration["model"] = args.model
    orchestration["model_meta"] = meta
    orchestration["raw_llm_response"] = response
    write_json(agent_path(args, "orchestration.json"), orchestration)
    log_step(f"agent: 编排写入 {agent_path(args, 'orchestration.json')}")
    return orchestration


def run_fastsurfer_for_subject(args: argparse.Namespace, subject: str) -> tuple[int, Path]:
    python = args.python if args.python.exists() else Path(sys.executable)
    input_subject = args.input_root / subject
    bids_subject = bids_subject_id(subject)
    shared_bids_root = bids_root(args)
    analysis_subject_root = shared_bids_root / "derivatives" / "FMRIPREP" / bids_subject
    output_root = analysis_subject_root / "fmriprep"
    subjects_dir = shared_bids_root / "derivatives" / "FASTSURFER"
    if not (shared_bids_root / bids_subject).exists():
        log_subject(subject, f"主分析 BIDS 不存在，先生成唯一 BIDS: {shared_bids_root}")
        env = subject_env(args, subject, "0")
        env["FMRI_BIDS_ONLY"] = "1"
        cmd = [str(python), str(PIPELINE), "bids"]
        log_path = agent_path(args, f"{subject}_prepare_bids.log")
        rc = run_streaming_command(cmd, log_path, env, label=subject)
        if rc != 0:
            return rc, subjects_dir
    fs_subject = expected_freesurfer_subject_id(shared_bids_root, bids_subject)
    existing_subject_dir = subjects_dir / fs_subject
    legacy_subject_dir = subjects_dir / bids_subject
    if fs_subject != bids_subject and not existing_subject_dir.exists() and fastsurfer_subject_complete(legacy_subject_dir):
        try:
            legacy_subject_dir.rename(existing_subject_dir)
            log_subject(subject, f"将旧 FastSurfer subject 目录重命名为 fMRIPrep 期待名称: {legacy_subject_dir} -> {existing_subject_dir}")
        except FileExistsError:
            pass
        except OSError as exc:
            log_subject(subject, f"重命名旧 FastSurfer subject 目录失败，将重新跑 FastSurfer: {type(exc).__name__}: {exc}")
    if fastsurfer_subject_complete(existing_subject_dir):
        log_subject(subject, f"发现可复用 FastSurfer 输出，跳过重跑: {existing_subject_dir}")
        write_json(
            output_root / "fastsurfer_reuse_status.json",
            {
                "reused": True,
                "subject_dir": str(existing_subject_dir),
                "bids_subject": bids_subject,
                "fastsurfer_subject": fs_subject,
                "reason": "已有 mri/surf/scripts 且 surface 文件兼容 fMRIPrep。",
            },
        )
        return 0, subjects_dir
    cmd = [
        str(python),
        str(FASTSURFER_PIPELINE),
        "fastsurfer",
        "--subject",
        bids_subject,
        "--fs-subject",
        fs_subject,
        "--input-subject",
        str(input_subject),
        "--output-root",
        str(output_root),
        "--bids-root",
        str(shared_bids_root),
        "--fastsurfer-subjects-dir",
        str(subjects_dir),
    ]
    log_path = agent_path(args, f"{subject}_fastsurfer.log")
    rc = run_streaming_command(cmd, log_path, analysis_env(args), label=subject)
    return rc, subjects_dir


def ensure_existing_surface_compat(subject_dir: Path) -> dict[str, object]:
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
    scripts = subject_dir / "scripts"
    if scripts.exists():
        write_json(scripts / "fmriprep_surface_compat.json", status)
    return status


def fastsurfer_subject_complete(subject_dir: Path) -> bool:
    if not subject_dir.exists():
        return False
    required_dirs = [subject_dir / "mri", subject_dir / "surf", subject_dir / "scripts"]
    if not all(path.exists() for path in required_dirs):
        return False
    compat = ensure_existing_surface_compat(subject_dir)
    return bool(compat.get("compatible"))


def execute_pipeline_for_subject(args: argparse.Namespace, subject: str, surface_mode: str, fs_subjects_dir: Path | None = None, jobs: int = 1) -> int:
    python = args.python if args.python.exists() else Path(sys.executable)
    env = subject_env(args, subject, surface_mode, jobs)
    if fs_subjects_dir:
        env["FMRI_FS_SUBJECTS_DIR"] = str(fs_subjects_dir)
    cmd = [str(python), str(PIPELINE), "full"]
    log_path = agent_path(args, f"{subject}_fmri-pipeline_analyze.log")
    return run_streaming_command(cmd, log_path, env, label=subject)


def pipeline_command_for_step(step: dict) -> str | None:
    skill = str(step.get("skill", ""))
    action = str(step.get("action", "run"))
    if skill == "fmri-pipeline" and action in {"analyze", "full", "run"}:
        return "full"
    if action not in {"run", ""}:
        return None
    return SKILL_TO_PIPELINE_COMMAND.get(skill)


def execute_pipeline_stage_for_subject(
    args: argparse.Namespace,
    subject: str,
    surface_mode: str,
    command: str,
    fs_subjects_dir: Path | None = None,
    jobs: int = 1,
    step_index: int = 0,
) -> int:
    python = args.python if args.python.exists() else Path(sys.executable)
    env = subject_env(args, subject, surface_mode, jobs)
    if fs_subjects_dir:
        env["FMRI_FS_SUBJECTS_DIR"] = str(fs_subjects_dir)
    cmd = [str(python), str(PIPELINE), command]
    log_path = agent_path(args, f"{subject}_step-{step_index:02d}_{command}.log")
    return run_streaming_command(cmd, log_path, env, label=subject)


def execute_one_subject(args: argparse.Namespace, subject: str, surface_mode: str, jobs: int) -> dict:
    log_subject(subject, f"开始，surface_mode={surface_mode}, subject_jobs={jobs}")
    fs_subjects_dir = None
    if surface_mode == "1":
        rc, fs_subjects_dir = run_fastsurfer_for_subject(args, subject)
        if rc != 0:
            return {"subject": subject, "stage": "fastsurfer", "returncode": rc, "surface_mode": surface_mode}
    rc = execute_pipeline_for_subject(args, subject, surface_mode, fs_subjects_dir, jobs)
    return {
        "subject": subject,
        "stage": "pipeline",
        "returncode": rc,
        "surface_mode": surface_mode,
        "fs_subjects_dir": str(fs_subjects_dir) if fs_subjects_dir else "",
    }


def execute_one_subject_steps(args: argparse.Namespace, subject: str, surface_mode: str, jobs: int, steps: list[dict]) -> dict:
    log_subject(subject, f"开始 split 编排，surface_mode={surface_mode}, subject_jobs={jobs}")
    fs_subjects_dir = None
    commands = [pipeline_command_for_step(step) for step in steps]
    needs_fmriprep_surface = any(command in {"fmriprep", "denoise", "segment", "timefreq", "full"} for command in commands)
    if surface_mode == "1" and needs_fmriprep_surface:
        rc, fs_subjects_dir = run_fastsurfer_for_subject(args, subject)
        if rc != 0:
            return {"subject": subject, "stage": "fastsurfer", "returncode": rc, "surface_mode": surface_mode}
    stage_results = []
    for index, step in enumerate(steps, start=1):
        command = pipeline_command_for_step(step)
        if command is None:
            stage_results.append({"step": step, "returncode": 0, "skipped": True, "reason": "未知或未授权步骤"})
            continue
        log_subject(subject, f"执行 split stage {index}/{len(steps)}: {command}")
        rc = execute_pipeline_stage_for_subject(args, subject, surface_mode, command, fs_subjects_dir, jobs, index)
        stage_results.append({"step": step, "command": command, "returncode": rc})
        if rc != 0:
            return {
                "subject": subject,
                "stage": command,
                "returncode": rc,
                "surface_mode": surface_mode,
                "fs_subjects_dir": str(fs_subjects_dir) if fs_subjects_dir else "",
                "stages": stage_results,
            }
    return {
        "subject": subject,
        "stage": "split",
        "returncode": 0,
        "surface_mode": surface_mode,
        "fs_subjects_dir": str(fs_subjects_dir) if fs_subjects_dir else "",
        "stages": stage_results,
    }


def execute_subjects(args: argparse.Namespace, subjects: list[str], surface_mode: str, orchestration: dict) -> int:
    results = []
    jobs = subject_jobs(args, surface_mode, len(subjects))
    steps = normalize_orchestration(orchestration, str(orchestration.get("main_task", ""))).get("steps", [])
    nthreads, omp = per_subject_threads(args, surface_mode, jobs)
    log_step(
        f"agent: 被试级并行数={jobs}; surface_mode={surface_mode}; "
        f"per-subject FMRIPREP_NTHREADS={nthreads}; FMRIPREP_OMP_NTHREADS={omp}; "
        f"MNI={getattr(args, 'resolved_mni_template', 'both')}; "
        f"CPU={DEFAULT_CPU_CORES} cores; GPU={DEFAULT_GPU_MEMORY_GB}GB"
    )
    log_step("agent: split stages = " + ", ".join(str(pipeline_command_for_step(step)) for step in steps))
    last_returncode = 0
    if jobs == 1:
        for subject in subjects:
            result = execute_one_subject_steps(args, subject, surface_mode, jobs, steps)
            result = attach_success_cleanup(args, result)
            results.append(result)
            rc = int(result.get("returncode", 1))
            if rc != 0:
                if last_returncode == 0:
                    last_returncode = rc
                append_error(
                    args.output_root,
                    f"subject={subject} stage={result.get('stage', '')} returncode={rc}",
                )
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            future_map = {executor.submit(execute_one_subject_steps, args, subject, surface_mode, jobs, steps): subject for subject in subjects}
            for future in concurrent.futures.as_completed(future_map):
                subject = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {"subject": subject, "stage": "exception", "returncode": 1, "error": f"{type(exc).__name__}: {exc}"}
                result = attach_success_cleanup(args, result)
                results.append(result)
                rc = int(result.get("returncode", 1))
                if rc != 0 and last_returncode == 0:
                    last_returncode = rc
                if rc != 0:
                    append_error(
                        args.output_root,
                        f"subject={subject} stage={result.get('stage', '')} returncode={rc} error={result.get('error', '')}",
                    )
    write_json(agent_path(args, "run_status.json"), {"returncode": last_returncode, "subjects": results, "orchestration": orchestration})
    return int(last_returncode)


def execute_orchestration(args: argparse.Namespace, orchestration: dict, task_text: str = "") -> int:
    task_text = task_text or str(orchestration.get("main_task", ""))
    subjects = orchestration.get("subjects") if isinstance(orchestration.get("subjects"), list) else None
    if not subjects:
        subjects = subjects_from_prompt_parse(getattr(args, "prompt_parse", None), args.input_root)
    if not subjects:
        subjects = resolve_run_subjects(args, task_text)
    surface_mode = str(orchestration.get("surface_mode") or "")
    if surface_mode not in {"0", "1"}:
        surface_mode = choose_surface_mode(args, task_text)
    mni_template = str(orchestration.get("mni_template") or "")
    if mni_template not in {*MNI_TEMPLATE_SPACES, "env"}:
        mni_template = choose_mni_template(args, task_text)
    original_orchestration = orchestration
    orchestration = normalize_orchestration(orchestration, task_text)
    for key in ("model", "model_meta", "raw_llm_response", "model_unavailable_reason"):
        if isinstance(original_orchestration, dict) and key in original_orchestration:
            orchestration[key] = original_orchestration[key]
    args.resolved_mni_template = mni_template
    orchestration["subjects"] = subjects
    orchestration["surface_mode"] = surface_mode
    orchestration["mni_template"] = mni_template
    orchestration["fmriprep_output_spaces"] = os.environ.get("FMRIPREP_OUTPUT_SPACES", MNI_TEMPLATE_SPACES.get(mni_template, ""))
    write_json(agent_path(args, "orchestration.json"), orchestration)
    return execute_subjects(args, subjects, surface_mode, orchestration)


def confirm_experiment_batch(experiments: list[Path], output_roots: list[Path], assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        log_step("agent: 检测到多个实验目录且当前不是交互终端；请加 --yes 确认批量顺序处理。")
        return False
    print("检测到多个实验目录，将按顺序处理：", flush=True)
    for exp, out in zip(experiments, output_roots):
        print(f"  - {exp.name}: input={exp} output={out}", flush=True)
    answer = input("确认按上述顺序处理所有实验？输入 yes 确认：").strip()
    return confirmed(answer)


def execute_experiment_batch(args: argparse.Namespace, command: str, task_text: str, experiments: list[Path]) -> int:
    surface_mode = infer_surface_mode(args, task_text)
    output_roots = [output_root_for_experiment(args.output_root, exp, surface_mode) for exp in experiments]
    batch_status_root = args.output_root
    batch_status_root.mkdir(parents=True, exist_ok=True)
    if not confirm_experiment_batch(experiments, output_roots, args.yes):
        write_json(current_agent_log_dir(batch_status_root) / "run_status.json", {"returncode": 3, "reason": "用户未确认批量实验处理。", "experiments": [str(p) for p in experiments]})
        return 3
    batch_results = []
    last_returncode = 0
    for exp, out in zip(experiments, output_roots):
        log_step(f"agent: 开始实验 {exp.name}: input={exp}, output={out}")
        exp_args = copy.copy(args)
        exp_args.input_root = exp
        exp_args.output_root = out
        exp_args.yes = True
        exp_args.agent_log_dir = getattr(args, "agent_log_dir", current_agent_log_dir(args.output_root))
        exp_args.output_root.mkdir(parents=True, exist_ok=True)
        write_json(agent_path(exp_args, "prompt_parse.json"), getattr(args, "prompt_parse", {}))
        status = doctor(exp_args)
        if command == "doctor":
            rc = 0 if status["ollama_binary"] and status["ollama_tags_status"] == 200 else 1
        elif command == "plan":
            build_plan(exp_args, status, task_text)
            rc = 0 if status["model_available"] else 2
        elif command == "analyze":
            orchestration = fallback_orchestration(task_text or "完整分析fmri数据")
            rc = execute_orchestration(exp_args, orchestration, task_text or orchestration["main_task"])
        else:
            if not status.get("model_available"):
                orchestration = fallback_orchestration(task_text)
                orchestration["model_unavailable_reason"] = "模型未加载或不可用，使用关键词规则编排。"
            else:
                orchestration = build_orchestration(exp_args, status, task_text)
            orchestration = prepare_orchestration_for_confirmation(exp_args, orchestration, task_text)
            rc = execute_orchestration(exp_args, orchestration, task_text)
        batch_results.append({"experiment": exp.name, "input_root": str(exp), "output_root": str(out), "returncode": rc})
        if rc != 0 and last_returncode == 0:
            last_returncode = rc
        if rc != 0:
            append_error(batch_status_root, f"experiment={exp.name} returncode={rc} output_root={out}")
            append_error(out, f"experiment={exp.name} returncode={rc}")
    batch_status = {"returncode": last_returncode, "experiments": batch_results}
    write_json(current_agent_log_dir(batch_status_root) / "experiment_batch_status.json", batch_status)
    return int(last_returncode)


def execute_orchestration_steps(args: argparse.Namespace, orchestration: dict) -> int:
    python = args.python if args.python.exists() else Path(sys.executable)
    env = analysis_env(args)
    steps = orchestration.get("steps", [])
    if not isinstance(steps, list) or not steps:
        steps = fallback_orchestration(str(orchestration.get("main_task", ""))).get("steps", [])
    last_returncode = 0
    for index, step in enumerate(steps, start=1):
        skill = str(step.get("skill", ""))
        action = str(step.get("action", ""))
        reason = str(step.get("reason", ""))
        log_step(f"agent: 执行第 {index}/{len(steps)} 步 skill={skill} action={action} reason={reason}")
        if skill == "fmri-pipeline" and action == "analyze":
            cmd = [str(python), str(PIPELINE), "analyze"]
            log_path = agent_path(args, f"step-{index:02d}_fmri-pipeline_analyze.log")
        elif skill == "fmri-fastsurfer-fmriprep" and action in {"doctor", "plan"}:
            cmd = [str(python), str(FASTSURFER_PIPELINE), action]
            log_path = agent_path(args, f"step-{index:02d}_fmri-fastsurfer-fmriprep_{action}.log")
        else:
            log_step(f"agent: 跳过未知或未授权步骤 skill={skill} action={action}")
            continue
        last_returncode = run_streaming_command(cmd, log_path, env)
        if last_returncode != 0:
            log_step(f"agent: 步骤失败，停止后续执行 returncode={last_returncode}")
            break
    write_json(agent_path(args, "run_status.json"), {"returncode": last_returncode, "orchestration": orchestration})
    return int(last_returncode)


def run_agent_task(args: argparse.Namespace, task_text: str) -> int:
    log_step(f"agent: 主要任务 = {task_text}")
    status = doctor(args)
    if not status.get("model_available"):
        log_step(f"agent: 模型未加载或不可用，使用关键词规则编排: {args.model}")
        orchestration = fallback_orchestration(task_text)
        return execute_orchestration(args, orchestration, task_text)
    orchestration = build_orchestration(args, status, task_text)
    return execute_orchestration(args, orchestration, task_text)


def prepare_orchestration_for_confirmation(args: argparse.Namespace, orchestration: dict, task_text: str) -> dict:
    subjects = subjects_from_prompt_parse(getattr(args, "prompt_parse", None), args.input_root) or parse_run_subjects(args, task_text)
    surface_mode = choose_surface_mode(args, task_text)
    mni_template = choose_mni_template(args, task_text)
    original_orchestration = orchestration
    orchestration = normalize_orchestration(orchestration, task_text)
    for key in ("model", "model_meta", "raw_llm_response", "model_unavailable_reason"):
        if isinstance(original_orchestration, dict) and key in original_orchestration:
            orchestration[key] = original_orchestration[key]
    orchestration["subjects"] = subjects
    orchestration["surface_mode"] = surface_mode
    orchestration["mni_template"] = mni_template
    orchestration["fmriprep_output_spaces"] = os.environ.get("FMRIPREP_OUTPUT_SPACES", MNI_TEMPLATE_SPACES.get(mni_template, ""))
    write_json(agent_path(args, "orchestration.json"), orchestration)
    return orchestration


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Local Ollama-powered fMRI Agent skill entrypoint.")
    p.add_argument(
        "command_or_task",
        nargs="?",
        help="doctor/plan/analyze/run，或直接写主要任务文本。不写时默认进入 run。",
    )
    p.add_argument("task", nargs="*", help="主要任务文本。")
    p.add_argument("--input-root", type=Path, default=None, help="待分析 fMRI 数据根目录；不指定时交互询问，默认 /data/input。")
    p.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help=f"最终分析结果输出目录；不指定时交互询问，默认按 surface 模式选择 {DEFAULT_FREE_OUTPUT_ROOT} 或 {DEFAULT_FAST_OUTPUT_ROOT}。",
    )
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST)
    p.add_argument("--ollama-timeout", type=int, default=120)
    p.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    p.add_argument("--fs-license", type=Path, default=DEFAULT_FS_LICENSE, help="FreeSurfer license.txt 路径；默认读取 FS_LICENSE。")
    p.add_argument(
        "--surface-mode",
        choices=["0", "1"],
        default=None,
        help="0=FreeSurfer/fMRIPrep 默认路径；1=FastSurfer 预跑并由 fMRIPrep 复用。",
    )
    p.add_argument(
        "--mni-template",
        choices=["both", "6", "2009"],
        default=None,
        help="fMRIPrep MNI 输出模板：both=两个模板；6=仅 MNI152NLin6Asym；2009=仅 MNI152NLin2009cAsym。也可用 FMRIPREP_OUTPUT_SPACES 完全覆盖。",
    )
    p.add_argument("--yes", action="store_true", help="未指定被试时确认分析 test_data/input 下所有一级被试文件夹。")
    p.add_argument(
        "--subject-jobs",
        type=int,
        default=None,
        help="被试级并行数；也可用 FMRI_SUBJECT_JOBS。FreeSurfer 模式默认按 24 核保守取 2，FastSurfer 模式默认 1。",
    )
    return p


def main() -> int:
    args = parser().parse_args()
    surface_mode_was_provided = args.surface_mode is not None
    known_commands = {"doctor", "plan", "analyze", "run"}
    if args.command_or_task in known_commands:
        command = args.command_or_task
        task_text = " ".join(args.task).strip()
    else:
        command = "run"
        parts = [part for part in [args.command_or_task, *args.task] if part]
        task_text = " ".join(parts).strip()
    if command == "run" and not task_text:
        task_text = default_task_text()

    prompt_parse = parse_user_prompt(args, command, task_text) if task_text else normalize_prompt_parse(None, task_text)
    if prompt_parse.get("main_task"):
        task_text = str(prompt_parse["main_task"])
    if not surface_mode_was_provided and str(prompt_parse.get("surface_mode", "")) in {"0", "1"}:
        args.surface_mode = str(prompt_parse["surface_mode"])
    if args.mni_template is None and str(prompt_parse.get("mni_template", "")) in MNI_TEMPLATE_SPACES:
        args.mni_template = str(prompt_parse["mni_template"])
    args.input_root = resolve_input_root(args, command, prompt_parse)
    args.input_root, prompt_parse, forced_subject = normalize_single_subject_input_root(args.input_root, prompt_parse)
    args.prompt_parse = prompt_parse
    args.output_root = resolve_output_root(args, command, task_text, prompt_parse)
    args.fs_license = resolve_fs_license(args, command)
    experiments = filter_experiments_from_prompt(discover_experiment_dirs(args.input_root), prompt_parse, task_text)
    if len(experiments) == 1 and experiments[0] != args.input_root:
        args.input_root = experiments[0]
    if len(experiments) == 1 and should_nest_output_for_experiment(args.input_root):
        args.output_root = output_root_for_experiment(args.output_root, args.input_root, infer_surface_mode(args, task_text))
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.agent_log_dir = init_agent_log_dir(args.output_root)
    log_step(f"入口启动: command={command}, model={args.model}")
    if forced_subject:
        log_step(f"agent: 检测到单被试输入目录，使用父目录 {args.input_root}，被试 {forced_subject}")
    log_step(f"analysis 输出目录 = {args.output_root}")
    log_step(f"agent 日志目录 = {args.agent_log_dir}")
    if len(experiments) > 1 and command in {"doctor", "plan", "analyze", "run"}:
        log_step(f"agent: 检测到 {len(experiments)} 个实验目录: {', '.join(exp.name for exp in experiments)}")
        return execute_experiment_batch(args, command, task_text, experiments)
    write_json(agent_path(args, "prompt_parse.json"), prompt_parse)
    status = doctor(args)
    if command == "doctor":
        print(json.dumps({"doctor": str(agent_path(args, "doctor.json")), "model_available": status["model_available"]}, ensure_ascii=False))
        return 0 if status["ollama_binary"] and status["ollama_tags_status"] == 200 else 1
    if command == "run":
        while True:
            if not status.get("model_available"):
                reason = (
                    f"模型未加载或不可用: {args.model}; "
                    f"OLLAMA_HOST={status.get('ollama_host')}; "
                    f"tags_status={status.get('ollama_tags_status')}; "
                    f"tags_error={status.get('ollama_tags_error')}; "
                    f"available_models={status.get('available_models')}"
                )
                log_step("agent: " + reason)
                orchestration = fallback_orchestration(task_text)
                orchestration["model_unavailable_reason"] = reason
            else:
                orchestration = build_orchestration(args, status, task_text)
            orchestration = prepare_orchestration_for_confirmation(args, orchestration, task_text)
            if confirm_parsed_command(args, orchestration, task_text):
                return execute_orchestration(args, orchestration, task_text)
            if not sys.stdin.isatty():
                write_json(agent_path(args, "run_status.json"), {"returncode": 3, "reason": "用户未确认解析后的命令。"})
                return 3
            if not surface_mode_was_provided:
                args.surface_mode = None
            task_text = prompt_task_text(task_text)
    plan = build_plan(args, status, task_text)
    if command == "plan":
        print(json.dumps({"plan": str(agent_path(args, "plan.json")), "model_available": status["model_available"]}, ensure_ascii=False))
        return 0 if status["model_available"] else 2
    if command == "analyze":
        orchestration = fallback_orchestration(task_text or "完整分析fmri数据")
        return execute_orchestration(args, orchestration, task_text or orchestration["main_task"])
    if not status["model_available"]:
        reason = (
            f"模型未加载或不可用: {args.model}; "
            f"OLLAMA_HOST={status.get('ollama_host')}; "
            f"tags_status={status.get('ollama_tags_status')}; "
            f"tags_error={status.get('ollama_tags_error')}; "
            f"available_models={status.get('available_models')}"
        )
        log_step("agent: " + reason)
        write_json(agent_path(args, "analysis_status.json"), {"returncode": 2, "reason": reason})
        return 2
    return run_analysis(args, plan)


if __name__ == "__main__":
    raise SystemExit(main())
