from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import ensure_parent, read_yaml, write_yaml
from sleep_ai_scientist.llm.client import extract_json_object

DOMAIN_TERMS = {
    "sleep",
    "insomnia",
    "eeg",
    "psg",
    "fmri",
    "dti",
    "mri",
    "rem",
    "nrem",
    "spindle",
}

VARIABLE_ALIASES = {
    "thalamus_DMN_FC": "thalamus default mode network functional connectivity",
    "thalamus_salience_FC": "thalamus salience network functional connectivity",
    "thalamus_frontoparietal_FC": "thalamus frontoparietal network functional connectivity",
    "DMN_FC": "default mode network functional connectivity",
    "salience_FC": "salience network functional connectivity",
    "frontoparietal_FC": "frontoparietal network functional connectivity",
    "timefreq_fALFF_0.01_0.08_over_0.01_0.25": "fALFF",
    "global_signal_psd_power_mean": "global signal",
    "global_signal_psd_power_max": "global signal",
    "mean_FD": "head motion framewise displacement",
    "thalamus_roi_voxels": "thalamus ROI voxel count",
    "DMN_roi_voxels": "default mode network ROI voxel count",
    "salience_roi_voxels": "salience network ROI voxel count",
    "frontoparietal_roi_voxels": "frontoparietal network ROI voxel count",
}

QUERY_GROUP = "experiment_feedback_expansion"


def build_literature_expansion_plan(
    experiment_summary: dict[str, Any],
    iteration_id: str,
    query_config_path: str | Path,
    *,
    llm_client: Any | None = None,
    llm_config: dict[str, Any] | None = None,
    max_queries: int = 8,
) -> dict[str, Any]:
    records = _experiment_records(experiment_summary)
    signals = _extract_signals(records)
    existing_queries = _existing_queries(Path(query_config_path))
    candidates = _rule_candidates(records, iteration_id)
    candidates.extend(_llm_candidates(records, iteration_id, llm_client, llm_config or {}))
    accepted, rejected = _validate_candidates(candidates, existing_queries, max_queries=max_queries)
    return {
        "iteration_id": iteration_id,
        "signals": signals,
        "candidate_count": len(candidates),
        "accepted_query_count": len(accepted),
        "accepted_queries": accepted,
        "rejected_duplicate_count": rejected["duplicate"],
        "rejected_invalid_count": rejected["invalid"],
        "rejected_queries": rejected["items"],
        "query_config": str(query_config_path),
        "skip_literature_refresh": len(accepted) == 0,
        "reason": "new_experiment_queries" if accepted else "no_new_experiment_queries",
    }


def append_queries_to_config(
    query_config_path: str | Path,
    accepted_queries: list[dict[str, Any]],
    *,
    group: str = QUERY_GROUP,
) -> dict[str, Any]:
    path = Path(query_config_path)
    payload = read_yaml(path)
    queries = payload.setdefault("query_sets", {}).setdefault("library", {}).setdefault("queries", {})
    existing = set(_normalize_query(query) for query in _flatten_queries(queries))
    target = queries.setdefault(group, [])
    appended = 0
    for item in accepted_queries:
        query = str(item.get("query", "")).strip()
        key = _normalize_query(query)
        if not query or key in existing:
            continue
        target.append(query)
        existing.add(key)
        appended += 1
    write_yaml(path, payload)
    return {"appended": appended, "group": group, "query_config": str(path)}


def write_intent_records(path: str | Path, records: list[dict[str, Any]]) -> None:
    out = ensure_parent(Path(path))
    with out.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _experiment_records(experiment_summary: dict[str, Any]) -> list[dict[str, Any]]:
    payload = experiment_summary.get("results_payload")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    direct = experiment_summary.get("experiment_results")
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, dict)]
    if any(key in experiment_summary for key in ["plan", "stats_result", "evidence_update"]):
        return [experiment_summary]
    return []


def _extract_signals(records: list[dict[str, Any]]) -> dict[str, int]:
    missing: set[str] = set()
    modality_gaps: set[str] = set()
    failed_tests = 0
    negative_control_failures = 0
    validated = 0
    for record in records:
        for test in _primary_tests(record):
            if not bool(test.get("passed", False)):
                failed_tests += 1
        for control in _negative_controls(record):
            if not bool(control.get("passed", True)):
                negative_control_failures += 1
        missing.update(_missing_variables(record))
        modality_gaps.update(_modality_gaps(record))
        if _reward(record) >= 0.7:
            validated += 1
    return {
        "records": len(records),
        "failed_tests": failed_tests,
        "negative_control_failures": negative_control_failures,
        "missing_variables": len(missing),
        "modality_gaps": len(modality_gaps),
        "validated_or_high_reward": validated,
    }


def _rule_candidates(records: list[dict[str, Any]], iteration_id: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for record in records:
        plan = record.get("plan", {}) if isinstance(record.get("plan"), dict) else {}
        source = _source_payload(record)
        source_hypothesis_id = str(plan.get("hypothesis_id") or source.get("hypothesis_id") or "")
        source_plan_id = str(plan.get("plan_id") or source.get("plan_id") or "")
        title_text = " ".join(str(plan.get(key, "")) for key in ["hypothesis_title", "hypothesis_content", "hypothesis_summary"])
        for test in _primary_tests(record):
            predictor = str(test.get("predictor", ""))
            outcome = str(test.get("outcome", ""))
            if not predictor or not outcome:
                continue
            if bool(test.get("passed", False)):
                if _reward(record) >= 0.7:
                    candidates.append(
                        _candidate(
                            f"{_pair_terms(predictor, outcome)} sleep fMRI",
                            "exploit_validated_pathway",
                            0.74,
                            "validated or high-reward primary pathway",
                            iteration_id,
                            source_hypothesis_id,
                            source_plan_id,
                        )
                    )
            else:
                candidates.append(
                    _candidate(
                        f"{_pair_terms(predictor, outcome)} sleep fMRI",
                        "resolve_failed_test",
                        0.86,
                        f"primary test failed for {predictor} -> {outcome}",
                        iteration_id,
                        source_hypothesis_id,
                        source_plan_id,
                    )
                )
                candidates.append(
                    _candidate(
                        f"null findings {_pair_terms(predictor, outcome)} sleep fMRI",
                        "resolve_failed_test",
                        0.71,
                        f"look for negative or conditional evidence for {predictor} -> {outcome}",
                        iteration_id,
                        source_hypothesis_id,
                        source_plan_id,
                    )
                )
        for control in _negative_controls(record):
            if bool(control.get("passed", True)):
                continue
            predictor = str(control.get("predictor", ""))
            outcome = str(control.get("outcome", ""))
            candidates.append(
                _candidate(
                    f"{_term(predictor)} {_term(outcome)} confound resting state fMRI sleep",
                    "probe_negative_control_failure",
                    0.88,
                    f"negative control failed for {predictor} -> {outcome}",
                    iteration_id,
                    source_hypothesis_id,
                    source_plan_id,
                )
            )
            if "global" in _term(outcome):
                candidates.append(
                    _candidate(
                        "sleep fMRI global signal regression fALFF",
                        "probe_negative_control_failure",
                        0.8,
                        "global signal negative control failure",
                        iteration_id,
                        source_hypothesis_id,
                        source_plan_id,
                    )
                )
        for variable in _missing_variables(record):
            candidates.append(
                _candidate(
                    f"{_term(variable)} measurement sleep fMRI",
                    "resolve_missing_measurement",
                    0.68,
                    f"missing measurement variable {variable}",
                    iteration_id,
                    source_hypothesis_id,
                    source_plan_id,
                )
            )
        gaps = _modality_gaps(record)
        if "dti" in gaps or "fractional anisotropy" in title_text.lower() or "fa" in title_text.lower():
            candidates.append(
                _candidate(
                    "fractional anisotropy thalamocortical spindle sleep DTI",
                    "fill_modality_gap",
                    0.83,
                    "hypothesis requests DTI/FA but experiment was fMRI constrained",
                    iteration_id,
                    source_hypothesis_id,
                    source_plan_id,
                )
            )
        if "eeg" in gaps or "psg" in gaps or "slow oscillation" in title_text.lower() or "spindle" in title_text.lower():
            candidates.append(
                _candidate(
                    "cortical slow oscillation thalamic spindle EEG fMRI sleep",
                    "fill_modality_gap",
                    0.82,
                    "hypothesis includes EEG/PSG spindle or slow-oscillation mechanisms",
                    iteration_id,
                    source_hypothesis_id,
                    source_plan_id,
                )
            )
            candidates.append(
                _candidate(
                    "sleep spindle density thalamus DMN functional connectivity EEG fMRI",
                    "fill_modality_gap",
                    0.79,
                    "bridge fMRI connectivity with EEG/PSG spindle outcomes",
                    iteration_id,
                    source_hypothesis_id,
                    source_plan_id,
                )
            )
        for confound in _confounds(record):
            candidates.append(
                _candidate(
                    f"{_term(confound)} confound thalamus DMN connectivity sleep fMRI",
                    "probe_confound_or_alternative_explanation",
                    0.76,
                    f"critic/model review identified confound {confound}",
                    iteration_id,
                    source_hypothesis_id,
                    source_plan_id,
                )
            )
    return candidates


def _llm_candidates(
    records: list[dict[str, Any]],
    iteration_id: str,
    llm_client: Any | None,
    llm_config: dict[str, Any],
) -> list[dict[str, Any]]:
    if llm_client is None or not bool(llm_config.get("enabled", False)):
        return []
    prompt = (
        "Return strict JSON with an intents array. Each intent must include intent_type, reason, "
        "priority, and candidate_queries. Generate literature search queries from these experiment results:\n"
        + json.dumps(records, ensure_ascii=False)[:12000]
    )
    try:
        if hasattr(llm_client, "call_json"):
            parsed = llm_client.call_json(
                [{"role": "user", "content": prompt}],
                max_tokens=int(llm_config.get("max_tokens", 1500)),
                temperature=llm_config.get("temperature", 0.0),
            )
        elif hasattr(llm_client, "complete"):
            response = llm_client.complete([{"role": "user", "content": prompt}], json_mode=True)
            content = getattr(response, "content", response)
            parsed = extract_json_object(str(content)) or {}
        else:
            content = llm_client(prompt)
            parsed = extract_json_object(str(content)) or {}
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for intent in parsed.get("intents", []):
        if not isinstance(intent, dict):
            continue
        for query in intent.get("candidate_queries", []):
            out.append(
                _candidate(
                    str(query),
                    str(intent.get("intent_type", "llm_experiment_intent")),
                    float(intent.get("priority", 0.7) or 0.7),
                    str(intent.get("reason", "LLM-generated experiment literature intent")),
                    iteration_id,
                    str(intent.get("source_hypothesis_id", "")),
                    str(intent.get("source_plan_id", "")),
                    source="llm",
                )
            )
    return out


def _validate_candidates(
    candidates: list[dict[str, Any]],
    existing_queries: set[str],
    *,
    max_queries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    rejected_items: list[dict[str, Any]] = []
    seen = set(existing_queries)
    duplicate = 0
    invalid = 0
    for item in sorted(candidates, key=lambda row: float(row.get("priority", 0)), reverse=True):
        query = _clean_query(str(item.get("query", "")))
        key = _normalize_query(query)
        if key in seen:
            duplicate += 1
            rejected_items.append({**item, "query": query, "rejection_reason": "duplicate"})
            continue
        reason = _invalid_reason(query)
        if reason:
            invalid += 1
            rejected_items.append({**item, "query": query, "rejection_reason": reason})
            continue
        accepted.append({**item, "query": query, "status": "accepted"})
        seen.add(key)
        if len(accepted) >= max_queries:
            break
    return accepted, {"duplicate": duplicate, "invalid": invalid, "items": rejected_items}


def _candidate(
    query: str,
    intent_type: str,
    priority: float,
    reason: str,
    iteration_id: str,
    hypothesis_id: str,
    plan_id: str,
    *,
    source: str = "rules",
) -> dict[str, Any]:
    return {
        "query": _clean_query(query),
        "intent_type": intent_type,
        "priority": round(float(priority), 3),
        "reason": reason,
        "source": source,
        "source_iteration": iteration_id,
        "source_hypothesis_id": hypothesis_id,
        "source_plan_id": plan_id,
        "status": "candidate",
    }


def _source_payload(record: dict[str, Any]) -> dict[str, Any]:
    feedback = record.get("evidence_update")
    return feedback if isinstance(feedback, dict) else {}


def _primary_tests(record: dict[str, Any]) -> list[dict[str, Any]]:
    stats = record.get("stats_result") if isinstance(record.get("stats_result"), dict) else {}
    tests = stats.get("tests") or record.get("primary_tests") or record.get("evidence_update", {}).get("primary_tests", [])
    return [item for item in tests if isinstance(item, dict)]


def _negative_controls(record: dict[str, Any]) -> list[dict[str, Any]]:
    controls = record.get("negative_control_results") or record.get("evidence_update", {}).get("negative_control_results", [])
    return [item for item in controls if isinstance(item, dict)]


def _missing_variables(record: dict[str, Any]) -> list[str]:
    plan = record.get("plan", {}) if isinstance(record.get("plan"), dict) else {}
    review = plan.get("metadata", {}).get("variable_mapping_review", {})
    values = review.get("missing_variables", []) if isinstance(review, dict) else []
    return [str(item) for item in values if str(item).strip()]


def _modality_gaps(record: dict[str, Any]) -> set[str]:
    plan = record.get("plan", {}) if isinstance(record.get("plan"), dict) else {}
    precheck = plan.get("metadata", {}).get("testability_precheck", {})
    gaps = set(str(item).strip().lower() for item in precheck.get("excluded_modalities", []) if str(item).strip()) if isinstance(precheck, dict) else set()
    reason = str(precheck.get("reason", "") if isinstance(precheck, dict) else "").lower()
    for modality in ["dti", "eeg", "psg", "mri", "scale"]:
        if modality in reason:
            gaps.add(modality)
    return gaps


def _confounds(record: dict[str, Any]) -> list[str]:
    review = record.get("evidence_update", {}).get("result_review", {})
    confounds = review.get("confounds", []) if isinstance(review, dict) else []
    return [str(item) for item in confounds if str(item).strip()]


def _reward(record: dict[str, Any]) -> float:
    update = record.get("evidence_update") if isinstance(record.get("evidence_update"), dict) else {}
    for key in ["support_score", "computed_reward"]:
        try:
            return float(update.get(key))
        except (TypeError, ValueError):
            pass
    return 0.0


def _existing_queries(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = read_yaml(path)
    queries = payload.get("query_sets", {}).get("library", {}).get("queries", {})
    return set(_normalize_query(query) for query in _flatten_queries(queries))


def _flatten_queries(payload: Any) -> list[str]:
    if isinstance(payload, list):
        return [str(item) for item in payload]
    if isinstance(payload, dict):
        rows: list[str] = []
        for value in payload.values():
            rows.extend(_flatten_queries(value))
        return rows
    return []


def _term(value: str) -> str:
    return VARIABLE_ALIASES.get(value, value.replace("_", " "))


def _pair_terms(left: str, right: str) -> str:
    left_term = _term(left)
    right_term = _term(right)
    if left_term.endswith("functional connectivity") and right_term.endswith("functional connectivity"):
        return f"{left_term.removesuffix(' functional connectivity')} {right_term}"
    return f"{left_term} {right_term}"


def _clean_query(query: str) -> str:
    query = re.sub(r"\b(?:hypothesis|plan)_[a-zA-Z0-9_]+\b", " ", query)
    query = re.sub(r"\bp\s*[<=>]\s*0?\.\d+\b", " ", query, flags=re.IGNORECASE)
    query = re.sub(r"[/\\][^\s]+", " ", query)
    return re.sub(r"\s+", " ", query).strip()


def _normalize_query(query: str) -> str:
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
    return " ".join(tokens)


def _invalid_reason(query: str) -> str:
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
    if len(tokens) < 4 or len(tokens) > 14:
        return "length"
    if not DOMAIN_TERMS & set(tokens):
        return "missing_domain_term"
    if re.search(r"\b(?:hypothesis|plan)_[a-zA-Z0-9_]+\b", query):
        return "internal_id"
    if "/" in query or "\\" in query:
        return "path_like"
    return ""
