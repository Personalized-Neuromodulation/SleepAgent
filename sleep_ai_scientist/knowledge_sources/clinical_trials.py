from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.knowledge_sources.base import make_id


def load_trial_queries(path: str | Path = "configs/clinical_trial_queries.yaml") -> tuple[str, list[dict[str, str]]]:
    payload = read_yaml(Path(path))
    version = payload.get("query_set", {}).get("version", "")
    queries = []
    for group, values in payload.get("trial_queries", {}).items():
        for query in values or []:
            queries.append({"query_group": str(group), "query_text": str(query), "query_set_version": version})
    return version, queries


def normalize_trial(study: dict[str, Any], query: dict[str, str]) -> dict[str, Any]:
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    arms = protocol.get("armsInterventionsModule", {})
    outcomes = protocol.get("outcomesModule", {})
    eligibility = protocol.get("eligibilityModule", {})
    contacts = protocol.get("contactsLocationsModule", {})
    sponsor = protocol.get("sponsorCollaboratorsModule", {})
    nct_id = identification.get("nctId", "")
    interventions = arms.get("interventions", []) or []
    return {
        "trial_id": make_id("trial", nct_id or identification.get("briefTitle", "")),
        "nct_id": nct_id,
        "brief_title": identification.get("briefTitle"),
        "official_title": identification.get("officialTitle"),
        "conditions_json": protocol.get("conditionsModule", {}).get("conditions", []) or [],
        "interventions_json": [item.get("name", "") for item in interventions],
        "intervention_types_json": [item.get("type", "") for item in interventions],
        "phase": ";".join(design.get("phases", []) or []),
        "status": status.get("overallStatus"),
        "study_type": design.get("studyType"),
        "allocation": design.get("designInfo", {}).get("allocation"),
        "masking": design.get("designInfo", {}).get("maskingInfo", {}).get("masking"),
        "primary_purpose": design.get("designInfo", {}).get("primaryPurpose"),
        "start_date": status.get("startDateStruct", {}).get("date"),
        "completion_date": status.get("completionDateStruct", {}).get("date"),
        "enrollment": design.get("enrollmentInfo", {}).get("count"),
        "enrollment_type": design.get("enrollmentInfo", {}).get("type"),
        "primary_outcomes_json": outcomes.get("primaryOutcomes", []) or [],
        "secondary_outcomes_json": outcomes.get("secondaryOutcomes", []) or [],
        "eligibility_json": eligibility,
        "minimum_age": eligibility.get("minimumAge"),
        "maximum_age": eligibility.get("maximumAge"),
        "sex": eligibility.get("sex"),
        "locations_json": contacts.get("locations", []) or [],
        "sponsor": sponsor.get("leadSponsor", {}).get("name"),
        "collaborators_json": sponsor.get("collaborators", []) or [],
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
        "query_text": query["query_text"],
        "query_group": query["query_group"],
        "retrieved_at": datetime.now(timezone.utc),
        "raw_json": study,
    }


def fetch_clinical_trials(config: dict[str, Any], queries_path: str | Path = "configs/clinical_trial_queries.yaml", session: Any | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    root = Path(config["_project_root"])
    version, queries = load_trial_queries(resolve_path(queries_path, root))
    cfg = config.get("clinical_trials", {})
    live_env = cfg.get("live_api_env", "SLEEPAGENT_ENABLE_CLINICALTRIALS_LIVE")
    if os.getenv(live_env, "").lower() not in {"1", "true", "yes"}:
        return [], [f"ClinicalTrials.gov live API skipped; set {live_env}=true to enable."]
    client = session or requests
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for query in queries:
        try:
            response = client.get(
                cfg.get("base_url", "https://clinicaltrials.gov/api/v2/studies"),
                params={"query.term": query["query_text"], "pageSize": int(cfg.get("max_results_per_query", 100))},
                timeout=float(cfg.get("timeout_seconds", 20)),
            )
            response.raise_for_status()
            payload = response.json()
            for study in payload.get("studies", []) or []:
                records.append(normalize_trial(study, query))
        except Exception as exc:
            warnings.append(f"{query['query_text']}: {exc}")
            if not cfg.get("fail_open", True):
                raise
    return records, warnings

