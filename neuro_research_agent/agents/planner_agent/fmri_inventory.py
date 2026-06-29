from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def progress_log(stage: str, agent: str, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{stage}] agent={agent} | {message}", flush=True)


def subject_alias(subject: str | None) -> str | None:
    if not subject:
        return None
    return subject if subject.startswith("sub-") else f"sub-{subject}"


def inspect_fmri_outputs(output_root: Path | None, subject: str | None = None, session: str | None = None) -> dict[str, Any]:
    if output_root is None:
        return {"available": False, "reason": "No fMRI output root supplied."}
    subject_id = subject_alias(subject)
    subject_dirs = [output_root / subject_id] if subject_id else sorted(output_root.glob("sub-*"))
    inventory: dict[str, Any] = {"available": output_root.exists(), "output_root": str(output_root), "subjects": []}
    for subject_idx, subject_dir in enumerate(subject_dirs, start=1):
        if not subject_dir.exists():
            continue
        progress_log("data_inventory", "fmri_inventory_agent.inspect_fmri_outputs", f"({subject_idx}/{len(subject_dirs)}) 扫描 subject={subject_dir.name}")
        subject_record = {"subject": subject_dir.name, "sessions": []}
        session_dirs = sorted(subject_dir.glob("ses-*"))
        for session_idx, ses_dir in enumerate(session_dirs, start=1):
            if session and ses_dir.name != session:
                continue
            progress_log("data_inventory", "fmri_inventory_agent.inspect_fmri_outputs", f"({subject_idx}/{len(subject_dirs)}) ({session_idx}/{len(session_dirs)}) 扫描 session={ses_dir.name}")
            record = {
                "session": ses_dir.name,
                "clean_bold": [str(p) for p in sorted((ses_dir / "clean_data" / "volume").glob("*.nii.gz"))],
                "surface_bold": [str(p) for p in sorted((ses_dir / "clean_data" / "surface").glob("*.func.gii"))],
                "qc_json": [str(p) for p in sorted((ses_dir / "qc_statistics").glob("*.json"))],
                "time_frequency": [str(p) for p in sorted((ses_dir / "time_frequency").rglob("*")) if p.is_file()],
                "segment_summary": str(ses_dir / "segment" / "segment_summary.json") if (ses_dir / "segment" / "segment_summary.json").exists() else "",
                "sleep_label": "",
                "events": [str(p) for p in sorted(ses_dir.rglob("*events.tsv"))],
            }
            subject_record["sessions"].append(record)
            progress_log("data_inventory", "fmri_inventory_agent.inspect_fmri_outputs", f"({subject_idx}/{len(subject_dirs)}) ({session_idx}/{len(session_dirs)}) 完成 session={ses_dir.name}")
        inventory["subjects"].append(subject_record)
        progress_log("data_inventory", "fmri_inventory_agent.inspect_fmri_outputs", f"({subject_idx}/{len(subject_dirs)}) 完成 subject={subject_dir.name}, sessions={len(subject_record['sessions'])}")
    return inventory


def available_data_types(inventory: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    for subject in inventory.get("subjects", []):
        for session in subject.get("sessions", []):
            if session.get("clean_bold"):
                types.add("clean_bold")
            if session.get("surface_bold"):
                types.add("surface_bold")
            if session.get("segment_summary"):
                types.add("sleep_label")
            if session.get("events"):
                types.add("events")
            if session.get("time_frequency"):
                types.add("time_frequency")
    return types
