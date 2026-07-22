from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from sleep_ai_scientist.storage.exporters import (
    export_clinical_trials_csv_jsonl,
    export_datasets_csv_jsonl,
    export_diagnostic_taxonomy_yaml_json,
    export_guidelines_csv_jsonl,
    export_instruments_yaml_json,
    export_knowledge_sources_manifest,
    export_knowledge_sources_report,
    export_standards_csv_jsonl,
    export_tools_methods_yaml_json,
)


def export_all_knowledge_sources(session: Session, paths: dict[str, Any], manifest: dict[str, Any], report: str) -> dict[str, Any]:
    outputs = {
        "clinical_trials": export_clinical_trials_csv_jsonl(session, paths["clinical_trials_csv"], paths["clinical_trials_jsonl"]),
        "guidelines": export_guidelines_csv_jsonl(session, paths["guidelines_csv"], paths["guidelines_jsonl"]),
        "standards": export_standards_csv_jsonl(session, paths["standards_csv"], paths["standards_jsonl"]),
        "diagnostic_taxonomy": export_diagnostic_taxonomy_yaml_json(session, paths["diagnostic_taxonomy_yaml"], paths["diagnostic_taxonomy_json"]),
        "datasets": export_datasets_csv_jsonl(session, paths["datasets_csv"], paths["datasets_jsonl"]),
        "instruments": export_instruments_yaml_json(session, paths["instruments_yaml"], paths["instruments_json"]),
        "tools_methods": export_tools_methods_yaml_json(session, paths["tools_methods_yaml"], paths["tools_methods_json"]),
    }
    outputs["manifest"] = export_knowledge_sources_manifest(manifest, paths["manifest"])
    outputs["report"] = export_knowledge_sources_report(report, paths["report"])
    return outputs

