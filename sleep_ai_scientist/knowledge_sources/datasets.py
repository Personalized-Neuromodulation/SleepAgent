from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.knowledge_sources.base import make_id


def build_dataset_records(config: dict[str, Any], source_path: str | Path = "configs/dataset_sources.yaml") -> list[dict[str, Any]]:
    payload = read_yaml(resolve_path(source_path, Path(config["_project_root"])))
    records = []
    for name, data in payload.get("datasets", {}).items():
        modalities = data.get("modality", [])
        records.append(
            {
                "dataset_id": make_id("dataset", name),
                "name": name,
                "source": data.get("source"),
                "url": data.get("url"),
                "modality_json": modalities,
                "population": data.get("population", ""),
                "species": data.get("species", "human"),
                "sample_size": data.get("sample_size"),
                "labels_available": True,
                "sleep_staging_available": "PSG" in modalities or "EEG" in modalities,
                "psg_available": "PSG" in modalities,
                "eeg_available": "EEG" in modalities,
                "fmri_available": "fMRI" in modalities,
                "dti_available": "DTI" in modalities,
                "mri_available": "MRI" in modalities,
                "scales_available": "questionnaires" in modalities or "clinical" in modalities,
                "access_status": data.get("access_status"),
                "license": data.get("license", ""),
                "benchmark_tasks_json": ["external_validation", "benchmark_planning"],
                "notes": data.get("notes", "Curated registry entry; no dataset download performed."),
            }
        )
    return records

