from __future__ import annotations

from collections import Counter
from typing import Any


def build_knowledge_sources_report(summary: dict[str, Any]) -> str:
    lines = [
        "# SleepAgent Knowledge Sources Report",
        "",
        "## Summary",
        "",
        f"* Registry version: {summary.get('registry_version', '')}",
        f"* Build time: {summary.get('created_at', '')}",
        f"* Enabled sources: {', '.join(summary.get('enabled_sources', []))}",
        f"* Database backend: {summary.get('database_backend', '')}",
        "",
        "## Clinical Trials",
        "",
        f"* Trial count: {summary.get('clinical_trials_count', 0)}",
        f"* Conditions: {summary.get('clinical_trial_conditions', {})}",
        f"* Intervention types: {summary.get('clinical_trial_intervention_types', {})}",
        f"* Recruiting / completed / unknown status count: {summary.get('clinical_trial_status_counts', {})}",
        "",
        "## Guidelines",
        "",
        f"* Guideline count: {summary.get('guidelines_count', 0)}",
        f"* Organizations: {summary.get('guideline_organizations', {})}",
        f"* Topics: {summary.get('guideline_topics', {})}",
        "* Recommendation metadata availability: metadata-only curated entries where full text is restricted.",
        "",
        "## Standards",
        "",
        f"* Standard count: {summary.get('standards_count', 0)}",
        "* AASM scoring manual metadata: included as metadata-only.",
        f"* Rule categories: {summary.get('standard_categories', {})}",
        "* Access restrictions note: restricted manual content is not downloaded or copied.",
        "",
        "## Diagnostic Taxonomy",
        "",
        f"* Term count: {summary.get('diagnostic_terms_count', 0)}",
        f"* Categories: {summary.get('diagnostic_categories', {})}",
        "* Source notes: curated taxonomy skeleton plus ICSD/MeSH metadata references.",
        "",
        "## Public Datasets",
        "",
        f"* Dataset count: {summary.get('datasets_count', 0)}",
        f"* Modalities: {summary.get('dataset_modalities', {})}",
        f"* Access status: {summary.get('dataset_access_status', {})}",
        "* Benchmark relevance: external validation and benchmark planning.",
        "",
        "## Instruments",
        "",
        f"* Instrument count: {summary.get('instruments_count', 0)}",
        f"* Domains: {summary.get('instrument_domains', {})}",
        "* Outcome / covariate roles: recorded per instrument.",
        "",
        "## Tools and Methods",
        "",
        f"* Tool/method count: {summary.get('tools_methods_count', 0)}",
        f"* Modalities: {summary.get('tool_method_modalities', {})}",
        f"* Analysis roles: {summary.get('tool_method_roles', {})}",
        "",
        "## Compliance Notes",
        "",
        "* No paywalled or restricted content downloaded.",
        "* AASM/ICSD restricted sources are metadata-only unless explicitly open.",
        "",
        "## Next Step",
        "",
        "* Use these registries together with Sleep Literature Library for Phase 1 Grounding.",
        "",
    ]
    return "\n".join(lines)


def counts(values: list[Any]) -> dict[str, int]:
    return dict(Counter(str(item) for item in values if item not in (None, "")))

