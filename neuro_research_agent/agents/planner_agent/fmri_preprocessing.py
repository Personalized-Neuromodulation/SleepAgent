from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from neuro_research_agent.core.io import write_json


DEFAULT_FMRI_LOCAL_AGENT_SCRIPT = Path(
    "/home/qlp/Agent_skills/fmri_local_split/agent_skills/fmri-local-agent/scripts/fmri_local_agent.py"
)


def progress_log(stage: str, agent: str, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{stage}] agent={agent} | {message}", flush=True)


def bids_subject_id(name: str) -> str:
    return name if name.startswith("sub-") else f"sub-{name}"


def _has_raw_imaging_data(path: Path) -> bool:
    if any(path.glob("ses-*")):
        return True
    if (path / "mri").is_dir() and any((path / "mri").rglob("*.dcm")):
        return True
    return any(path.rglob("*.dcm")) or any(path.rglob("*.nii")) or any(path.rglob("*.nii.gz"))


def _looks_like_raw_subject(path: Path) -> bool:
    return path.is_dir() and not path.name.startswith(".") and (path.name.startswith("sub-") or _has_raw_imaging_data(path))


def raw_subject_dirs(raw_input_root: Path | None) -> list[Path]:
    if raw_input_root is None or not raw_input_root.exists():
        return []
    if raw_input_root.name.startswith("sub-"):
        return [raw_input_root]
    if _looks_like_raw_subject(raw_input_root):
        children = [child for child in raw_input_root.iterdir() if child.is_dir() and not child.name.startswith(".")]
        if not any(_looks_like_raw_subject(child) for child in children):
            return [raw_input_root]
    return sorted(child for child in raw_input_root.iterdir() if _looks_like_raw_subject(child))


def raw_experiment_root(raw_input_root: Path | None) -> Path | None:
    if raw_input_root is None:
        return None
    if raw_input_root.name.startswith("sub-"):
        return raw_input_root.parent
    subjects = raw_subject_dirs(raw_input_root)
    if len(subjects) == 1 and subjects[0] == raw_input_root and raw_input_root.name.startswith("sub-"):
        return raw_input_root.parent
    return raw_input_root


def requested_subject_names(raw_input_root: Path | None) -> list[str]:
    if raw_input_root is not None and raw_input_root.name.startswith("sub-"):
        return [raw_input_root.name]
    subjects = raw_subject_dirs(raw_input_root)
    if len(subjects) == 1 and raw_input_root is not None and subjects[0] == raw_input_root and raw_input_root.name.startswith("sub-"):
        return [raw_input_root.name]
    return []


def expected_processed_fmri_root(raw_input_root: Path | None, fmri_result_root: Path | None, processed_root: Path | None = None) -> Path | None:
    if processed_root is not None:
        if processed_root.name == "derivatives":
            return processed_root.parent
        return processed_root
    if fmri_result_root is None:
        return None
    if fmri_result_root.name in {"fmri_free", "fmri_fast", "analysis_free", "analysis_fast"}:
        return fmri_result_root
    if raw_input_root is not None:
        experiment_root = raw_experiment_root(raw_input_root)
        if experiment_root is not None:
            return fmri_result_root / experiment_root.name / "fmri_free"
    return fmri_result_root


def derivatives_root(processed_root: Path) -> Path:
    return processed_root if processed_root.name == "derivatives" else processed_root / "derivatives"


def _session_names_from_raw(subject_dir: Path) -> list[str]:
    sessions = sorted(path.name for path in subject_dir.glob("ses-*") if path.is_dir())
    return sessions


def _qc_figures(session_dir: Path) -> list[str]:
    files: list[Path] = []
    for rel in ("figures", "qc_statistics"):
        root = session_dir / rel
        if root.exists():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".svg", ".html", ".png", ".jpg", ".jpeg"}
            )
    return [str(path) for path in sorted(files)]


def inspect_processed_fmri_completion(processed_root: Path | None, raw_input_root: Path | None = None) -> dict[str, Any]:
    if processed_root is None:
        return {"complete": False, "reason": "No processed fMRI root supplied.", "subjects": []}
    deriv_root = derivatives_root(processed_root)
    raw_subjects = raw_subject_dirs(raw_input_root)
    expected_subjects = [bids_subject_id(path.name) for path in raw_subjects]
    if not expected_subjects and deriv_root.exists():
        expected_subjects = [path.name for path in sorted(deriv_root.glob("sub-*")) if path.is_dir()]

    status: dict[str, Any] = {
        "complete": False,
        "processed_root": str(processed_root),
        "derivatives_root": str(deriv_root),
        "derivatives_exists": deriv_root.exists(),
        "expected_subject_count": len(expected_subjects),
        "subjects": [],
        "missing": [],
    }
    if not deriv_root.exists():
        status["missing"].append(f"derivatives directory missing: {deriv_root}")
        return status
    if not expected_subjects:
        status["missing"].append("No expected subjects found from raw input or derivatives.")
        return status

    raw_by_bids = {bids_subject_id(path.name): path for path in raw_subjects}
    for subject_id in expected_subjects:
        subject_dir = deriv_root / subject_id
        subject_record: dict[str, Any] = {
            "subject": subject_id,
            "complete": False,
            "subject_dir": str(subject_dir),
            "sessions": [],
            "missing": [],
        }
        if not subject_dir.exists():
            subject_record["missing"].append("subject derivatives directory missing")
            status["missing"].append(f"{subject_id}: subject derivatives directory missing")
            status["subjects"].append(subject_record)
            continue

        qc_json = sorted((subject_dir / "logs").glob("*qc*.json"))
        html_reports = sorted((subject_dir / "fmriprep" / "output").glob("*.html"))
        subject_record["qc_json"] = [str(path) for path in qc_json]
        subject_record["html_reports"] = [str(path) for path in html_reports]
        if not qc_json and not html_reports:
            subject_record["missing"].append("subject-level QC JSON or fMRIPrep HTML report missing")

        raw_sessions = _session_names_from_raw(raw_by_bids[subject_id]) if subject_id in raw_by_bids else []
        session_names = raw_sessions or [path.name for path in sorted(subject_dir.glob("ses-*")) if path.is_dir()]
        if not session_names:
            subject_record["missing"].append("no session directories found")
        for session_name in session_names:
            session_dir = subject_dir / session_name
            clean_bold = sorted((session_dir / "clean_data" / "volume").glob("*.nii.gz"))
            qc_figures = _qc_figures(session_dir)
            session_record = {
                "session": session_name,
                "complete": bool(session_dir.exists() and clean_bold and qc_figures),
                "session_dir": str(session_dir),
                "clean_bold": [str(path) for path in clean_bold],
                "qc_figures": qc_figures,
                "missing": [],
            }
            if not session_dir.exists():
                session_record["missing"].append("session derivatives directory missing")
            if not clean_bold:
                session_record["missing"].append("clean_data/volume NIfTI missing")
            if not qc_figures:
                session_record["missing"].append("QC figures missing under figures/ or qc_statistics/")
            for item in session_record["missing"]:
                status["missing"].append(f"{subject_id}/{session_name}: {item}")
            subject_record["sessions"].append(session_record)
        subject_record["complete"] = not subject_record["missing"] and all(item["complete"] for item in subject_record["sessions"])
        for item in subject_record["missing"]:
            status["missing"].append(f"{subject_id}: {item}")
        status["subjects"].append(subject_record)

    status["complete"] = not status["missing"] and all(item["complete"] for item in status["subjects"])
    return status


def run_fmri_local_split_agent(
    raw_input_root: Path,
    fmri_result_root: Path,
    task_text: str,
    log_dir: Path,
    agent_script: Path | None = None,
) -> dict[str, Any]:
    script = agent_script or DEFAULT_FMRI_LOCAL_AGENT_SCRIPT
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "fmri_local_split_run.log"
    agent_input_root = raw_experiment_root(raw_input_root) or raw_input_root
    subjects = requested_subject_names(raw_input_root)
    subject_suffix = " ".join(subjects)
    agent_task_text = " ".join(part for part in [task_text or "完整分析fmri数据", subject_suffix] if part).strip()
    cmd = [
        sys.executable,
        str(script),
        "run",
        agent_task_text,
        "--input-root",
        str(agent_input_root),
        "--output-root",
        str(fmri_result_root),
        "--yes",
    ]
    started = time.time()
    progress_log("fmri_preprocessing", "fmri_local_split_agent", f"启动 fMRI 预处理: input={agent_input_root}, output={fmri_result_root}, subjects={subjects or 'all'}")
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.run(cmd, text=True, stdout=log_file, stderr=subprocess.STDOUT)
    record = {
        "command": cmd,
        "agent_input_root": str(agent_input_root),
        "subjects": subjects,
        "returncode": process.returncode,
        "elapsed_seconds": int(time.time() - started),
        "log": str(log_path),
    }
    write_json(log_dir / "fmri_local_split_run.json", record)
    return record


def ensure_processed_fmri_data(
    raw_input_root: Path | None,
    fmri_result_root: Path | None,
    processed_root: Path | None,
    task_text: str,
    output_dir: Path,
    agent_script: Path | None = None,
) -> dict[str, Any]:
    expected_root = expected_processed_fmri_root(raw_input_root, fmri_result_root, processed_root)
    before = inspect_processed_fmri_completion(expected_root, raw_input_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    precheck_path = output_dir / "data" / "fmri_derivatives_precheck.json"
    write_json(precheck_path, before)
    status: dict[str, Any] = {
        "processed_root": str(expected_root) if expected_root else "",
        "used_existing_processed_data": bool(before.get("complete")),
        "preprocess_run": None,
        "before": before,
        "after": before,
        "precheck_json": str(precheck_path),
    }
    if before.get("complete"):
        progress_log("fmri_preprocessing", "fmri_preprocessing_agent.inspect_derivatives", f"处理后的 fMRI derivatives/QC 完整，直接读取: {expected_root}")
        return status
    missing = before.get("missing", [])
    progress_log(
        "fmri_preprocessing",
        "fmri_preprocessing_agent.inspect_derivatives",
        f"处理后的 fMRI derivatives/QC 不完整: processed_root={expected_root}, missing_count={len(missing)}, precheck={precheck_path}",
    )
    for item in missing[:20]:
        progress_log("fmri_preprocessing", "fmri_preprocessing_agent.inspect_derivatives", f"缺失项: {item}")
    if len(missing) > 20:
        progress_log("fmri_preprocessing", "fmri_preprocessing_agent.inspect_derivatives", f"其余缺失项 {len(missing) - 20} 条见 {precheck_path}")
    if raw_input_root is None or fmri_result_root is None:
        status["reason"] = "Processed fMRI output is incomplete, but raw_fmri_input_root or fmri_result_root is missing."
        return status
    run_record = run_fmri_local_split_agent(raw_input_root, fmri_result_root, "完整分析fmri数据", output_dir / "fmri_preprocessing", agent_script)
    status["preprocess_run"] = run_record
    after = inspect_processed_fmri_completion(expected_root, raw_input_root)
    status["after"] = after
    status["used_existing_processed_data"] = False
    status["processed_root"] = str(expected_root) if expected_root else ""
    status["complete"] = bool(after.get("complete"))
    return status
