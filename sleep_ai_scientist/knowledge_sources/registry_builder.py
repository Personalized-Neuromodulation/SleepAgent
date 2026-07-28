from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import load_config, resolve_path
from sleep_ai_scientist.knowledge_sources.clinical_trials import fetch_clinical_trials
from sleep_ai_scientist.knowledge_sources.datasets import build_dataset_records
from sleep_ai_scientist.knowledge_sources.diagnostic_taxonomy import build_diagnostic_terms
from sleep_ai_scientist.knowledge_sources.guidelines import build_guideline_records
from sleep_ai_scientist.knowledge_sources.instruments import build_instrument_records
from sleep_ai_scientist.knowledge_sources.registry_exporters import export_all_knowledge_sources
from sleep_ai_scientist.knowledge_sources.registry_report import build_knowledge_sources_report, counts
from sleep_ai_scientist.knowledge_sources.standards import build_standard_records
from sleep_ai_scientist.knowledge_sources.tools_methods import build_tool_method_records
from sleep_ai_scientist.storage.db import create_engine_from_config, database_url_from_config, init_database, session_scope
from sleep_ai_scientist.storage.repositories import (
    ClinicalTrialRepository,
    DatasetRepository,
    DiagnosticTermRepository,
    GuidelineRepository,
    InstrumentRepository,
    RunRepository,
    StandardRuleRepository,
    ToolMethodRepository,
)
from sleep_ai_scientist.storage.models import ClinicalTrial, DiagnosticTerm, Guideline, Instrument, PublicDataset, StandardRule, ToolMethod
from sqlalchemy import select, func


def _paths(config: dict[str, Any]) -> dict[str, str]:
    root = Path(config["_project_root"])
    return {key: str(resolve_path(value, root)) for key, value in config.get("paths", {}).items()}


def _enabled(config: dict[str, Any], key: str) -> bool:
    return bool(config.get(key, {}).get("enabled", False))


def _upsert_all(session, repo, rows: list[dict[str, Any]]) -> None:  # type: ignore[no-untyped-def]
    for row in rows:
        repo.upsert(session, row)


def build_knowledge_sources(
    config_path_value: str | Path = "configs/knowledge_sources_config.yaml",
    *,
    backend: str | None = "postgresql",
    clinical_trials_session: Any | None = None,
) -> dict[str, Any]:
    config = load_config(config_path_value)
    root = Path(config["_project_root"])
    db_config_path = resolve_path(config.get("database_config", "configs/database_config.yaml"), root)
    engine = create_engine_from_config(db_config_path, backend=backend)
    init_database(engine)
    _, db_url = database_url_from_config(load_config(db_config_path), backend=backend)
    registry_version = config.get("project", {}).get("registry_version", "sleepagent_knowledge_sources_v1")
    paths = _paths(config)
    enabled_sources = []
    warnings: list[str] = []

    with session_scope(engine) as session:
        run = RunRepository().create_run(session, "knowledge_sources_build", str(config_path_value), corpus_version=registry_version)
        clinical_trials = []
        if _enabled(config, "clinical_trials"):
            enabled_sources.append("clinical_trials")
            clinical_trials, trial_warnings = fetch_clinical_trials(config, session=clinical_trials_session)
            warnings.extend(trial_warnings)
            _upsert_all(session, ClinicalTrialRepository(), clinical_trials)
        guidelines = build_guideline_records(config) if _enabled(config, "guidelines") else []
        if guidelines:
            enabled_sources.append("guidelines")
            _upsert_all(session, GuidelineRepository(), guidelines)
        standards = build_standard_records(config) if _enabled(config, "standards") else []
        if standards:
            enabled_sources.append("standards")
            _upsert_all(session, StandardRuleRepository(), standards)
        diagnostic_terms = build_diagnostic_terms(config) if _enabled(config, "diagnostic_taxonomy") else []
        if diagnostic_terms:
            enabled_sources.append("diagnostic_taxonomy")
            _upsert_all(session, DiagnosticTermRepository(), diagnostic_terms)
        datasets = build_dataset_records(config) if _enabled(config, "datasets") else []
        if datasets:
            enabled_sources.append("datasets")
            _upsert_all(session, DatasetRepository(), datasets)
        instruments = build_instrument_records(config) if _enabled(config, "instruments") else []
        if instruments:
            enabled_sources.append("instruments")
            _upsert_all(session, InstrumentRepository(), instruments)
        tools_methods = build_tool_method_records(config) if _enabled(config, "tools_methods") else []
        if tools_methods:
            enabled_sources.append("tools_methods")
            _upsert_all(session, ToolMethodRepository(), tools_methods)

        summary = _summary(
            registry_version,
            enabled_sources,
            backend or "postgresql",
            clinical_trials,
            guidelines,
            standards,
            diagnostic_terms,
            datasets,
            instruments,
            tools_methods,
            paths,
            warnings,
        )
        report = build_knowledge_sources_report(summary)
        outputs = export_all_knowledge_sources(session, paths, summary, report)
        RunRepository().finish_run(session, run.run_id, "completed")
        summary["run_id"] = run.run_id
        summary["exports"] = {key: value for key, value in outputs.items() if key != "manifest"}
    engine.dispose()
    return summary


def export_knowledge_sources(config_path_value: str | Path = "configs/knowledge_sources_config.yaml", *, backend: str | None = "postgresql") -> dict[str, Any]:
    config = load_config(config_path_value)
    root = Path(config["_project_root"])
    db_config_path = resolve_path(config.get("database_config", "configs/database_config.yaml"), root)
    engine = create_engine_from_config(db_config_path, backend=backend)
    init_database(engine)
    paths = _paths(config)
    summary = {
        "registry_version": config.get("project", {}).get("registry_version", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "enabled_sources": [],
        "database_backend": backend or "postgresql",
        "notes": "Export from existing database state.",
    }
    with session_scope(engine) as session:
        counts_payload = {
            "clinical_trials_count": int(session.scalar(select(func.count()).select_from(ClinicalTrial)) or 0),
            "guidelines_count": int(session.scalar(select(func.count()).select_from(Guideline)) or 0),
            "standards_count": int(session.scalar(select(func.count()).select_from(StandardRule)) or 0),
            "diagnostic_terms_count": int(session.scalar(select(func.count()).select_from(DiagnosticTerm)) or 0),
            "datasets_count": int(session.scalar(select(func.count()).select_from(PublicDataset)) or 0),
            "instruments_count": int(session.scalar(select(func.count()).select_from(Instrument)) or 0),
            "tools_methods_count": int(session.scalar(select(func.count()).select_from(ToolMethod)) or 0),
        }
        summary.update(counts_payload)
        summary["output_files"] = {key: value for key, value in paths.items() if key not in {"outputs_dir", "registries_dir"}}
        outputs = export_all_knowledge_sources(session, paths, summary, build_knowledge_sources_report(summary))
    engine.dispose()
    return {"output_files": outputs}


def generate_knowledge_sources_report(config_path_value: str | Path = "configs/knowledge_sources_config.yaml", *, backend: str | None = "postgresql") -> dict[str, Any]:
    return export_knowledge_sources(config_path_value, backend=backend)


def _summary(
    registry_version: str,
    enabled_sources: list[str],
    database_backend: str,
    clinical_trials: list[dict[str, Any]],
    guidelines: list[dict[str, Any]],
    standards: list[dict[str, Any]],
    diagnostic_terms: list[dict[str, Any]],
    datasets: list[dict[str, Any]],
    instruments: list[dict[str, Any]],
    tools_methods: list[dict[str, Any]],
    paths: dict[str, str],
    warnings: list[str],
) -> dict[str, Any]:
    output_files = {key: value for key, value in paths.items() if key not in {"outputs_dir", "registries_dir"}}
    return {
        "registry_version": registry_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "enabled_sources": enabled_sources,
        "clinical_trials_count": len(clinical_trials),
        "guidelines_count": len(guidelines),
        "standards_count": len(standards),
        "diagnostic_terms_count": len(diagnostic_terms),
        "datasets_count": len(datasets),
        "instruments_count": len(instruments),
        "tools_methods_count": len(tools_methods),
        "output_files": output_files,
        "database_backend": database_backend,
        "notes": "Metadata-only for restricted AASM/ICSD sources; no paywalled content downloaded.",
        "warnings": warnings,
        "clinical_trial_conditions": counts([condition for row in clinical_trials for condition in row.get("conditions_json", [])]),
        "clinical_trial_intervention_types": counts([kind for row in clinical_trials for kind in row.get("intervention_types_json", [])]),
        "clinical_trial_status_counts": counts([row.get("status") for row in clinical_trials]),
        "guideline_organizations": counts([row.get("organization") for row in guidelines]),
        "guideline_topics": counts([row.get("topic") for row in guidelines]),
        "standard_categories": counts([row.get("rule_category") for row in standards]),
        "diagnostic_categories": counts([row.get("category") for row in diagnostic_terms]),
        "dataset_modalities": counts([modality for row in datasets for modality in row.get("modality_json", [])]),
        "dataset_access_status": counts([row.get("access_status") for row in datasets]),
        "instrument_domains": counts([row.get("domain") for row in instruments]),
        "tool_method_modalities": counts([row.get("modality") for row in tools_methods]),
        "tool_method_roles": counts([role for row in tools_methods for role in row.get("role_json", [])]),
    }
