from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from neuro_research_agent.agents.planner_agent.fmri_inventory import available_data_types as fmri_available_data_types
from neuro_research_agent.agents.planner_agent.fmri_inventory import inspect_fmri_outputs


def progress_log(stage: str, agent: str, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{stage}] agent={agent} | {message}", flush=True)


MODALITY_PATTERNS: dict[str, list[str]] = {
    "clean_bold": ["**/clean_data/volume/*.nii.gz", "**/*_bold.nii", "**/*_bold.nii.gz"],
    "surface_bold": ["**/clean_data/surface/*.func.gii", "**/*.func.gii"],
    "events": ["**/*events.tsv", "**/*events.csv", "**/*events.json"],
    "sleep_label": ["**/segment/segment_summary.json", "**/*sleep*stage*.csv", "**/*sleep*stage*.tsv"],
    "time_frequency": ["**/time_frequency/**/*", "**/*timefreq*.csv", "**/*spectrogram*.npy"],
    "eeg": ["**/*.edf", "**/*.bdf", "**/*.set", "**/*.fif", "**/*eeg*.csv", "**/*eeg*.tsv"],
    "meg": ["**/*meg*.fif", "**/*.ds", "**/*-meg.fif"],
    "ephys_spikes": ["**/*spike*.npy", "**/*spike*.csv", "**/*units*.tsv", "**/*sorting*.json"],
    "lfp": ["**/*lfp*.npy", "**/*lfp*.csv", "**/*lfp*.mat"],
    "behavior": ["**/*behavior*.csv", "**/*behav*.csv", "**/*trial*.csv", "**/*task*.csv"],
    "eye_tracking": ["**/*eye*.csv", "**/*gaze*.csv", "**/*pupil*.csv", "**/*.asc"],
    "physiology": ["**/*physio*.tsv", "**/*resp*.csv", "**/*ecg*.csv", "**/*heart*.csv"],
    "structural_mri": ["**/*_T1w.nii", "**/*_T1w.nii.gz", "**/*_T2w.nii", "**/*_T2w.nii.gz"],
    "dwi": ["**/*_dwi.nii", "**/*_dwi.nii.gz", "**/*.bvec", "**/*.bval"],
    "pet": ["**/*pet*.nii", "**/*pet*.nii.gz", "**/*_pet.json"],
    "calcium_imaging": ["**/*calcium*.npy", "**/*suite2p*/**/*.npy", "**/*caiman*/**/*.hdf5"],
    "omics": ["**/*rna*.csv", "**/*transcript*.tsv", "**/*gene*.csv", "**/*cell*.h5ad"],
    "labels": ["**/*label*.csv", "**/*labels*.tsv", "**/*condition*.csv", "**/*phenotype*.csv"],
}


def inspect_neuroscience_data(data_root: Path | None, subject: str | None = None, session: str | None = None) -> dict[str, Any]:
    if data_root is None:
        return {"available": False, "reason": "No neuroscience data root supplied.", "modalities": {}}
    inventory: dict[str, Any] = {
        "available": data_root.exists(),
        "data_root": str(data_root),
        "subject": subject or "",
        "session": session or "",
        "modalities": {},
    }
    if not data_root.exists():
        inventory["reason"] = "Data root does not exist."
        return inventory
    for idx, (modality, patterns) in enumerate(MODALITY_PATTERNS.items(), start=1):
        progress_log("data_inventory", "data_inventory_agent.inspect_neuroscience_data", f"({idx}/{len(MODALITY_PATTERNS)}) 扫描 modality={modality}")
        files: list[str] = []
        for pattern in patterns:
            files.extend(str(path) for path in sorted(data_root.glob(pattern)) if path.is_file())
        deduped = sorted(set(files))
        inventory["modalities"][modality] = {
            "count": len(deduped),
            "examples": deduped[:20],
        }
        progress_log("data_inventory", "data_inventory_agent.inspect_neuroscience_data", f"({idx}/{len(MODALITY_PATTERNS)}) 完成 modality={modality}, count={len(deduped)}")
    bids_markers = [data_root / "dataset_description.json", data_root / "participants.tsv"]
    inventory["bids_like"] = any(path.exists() for path in bids_markers)
    return inventory


def available_data_types(inventory: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    for modality, payload in inventory.get("modalities", {}).items():
        if int(payload.get("count", 0)) > 0:
            types.add(modality)
    if inventory.get("fmri_inventory"):
        types.update(fmri_available_data_types(inventory["fmri_inventory"]))
    return types


def inspect_all_data(
    data_root: Path | None,
    fmri_output_root: Path | None,
    subject: str | None = None,
    session: str | None = None,
) -> dict[str, Any]:
    primary_root = data_root or fmri_output_root
    inventory = inspect_neuroscience_data(primary_root, subject, session)
    if fmri_output_root is not None:
        progress_log("data_inventory", "fmri_inventory_agent.inspect_fmri_outputs", f"开始扫描已处理 fMRI 输出目录: {fmri_output_root}")
        inventory["fmri_inventory"] = inspect_fmri_outputs(fmri_output_root, subject, session)
        progress_log("data_inventory", "fmri_inventory_agent.inspect_fmri_outputs", "已处理 fMRI 输出目录扫描完成")
    return inventory
