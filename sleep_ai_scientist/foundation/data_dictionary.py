from __future__ import annotations

from pathlib import Path

from sleep_ai_scientist.common.io import write_yaml
from sleep_ai_scientist.schemas.foundation import DataDictionaryEntry, FeatureRegistryRecord


def build_data_dictionary(records: list[FeatureRegistryRecord]) -> list[DataDictionaryEntry]:
    entries = []
    for record in records:
        entries.append(
            DataDictionaryEntry(
                variable=record.feature_name,
                modality=record.modality,
                role=record.role.value if hasattr(record.role, "value") else str(record.role),
                description=record.description,
                unit=record.unit,
                source_file=record.source_file,
                source_column=record.source_column,
                allowed_values=["HC", "INS"] if record.feature_name == "group" else None,
                valid_range=None,
            )
        )
    return entries


def write_data_dictionary(entries: list[DataDictionaryEntry], path: Path) -> None:
    write_yaml(path, {"variables": [entry.model_dump(mode="json") for entry in entries]})
