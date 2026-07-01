from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_csv
from sleep_ai_scientist.schemas.literature import LiteratureRecord

STOP = {"the", "and", "with", "from", "that", "this", "sleep", "brain", "study", "analysis", "effect", "effects"}
IMPORTANT = {"spindle", "orexin", "gaba", "adenosine", "glymphatic", "thalamocortical", "optogenetic", "polysomnography", "fmri", "dti", "insomnia", "circadian"}


def _tokens(text: str) -> list[str]:
    return [item for item in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", text.lower()) if item not in STOP]


def generate_query_expansion_candidates(records: list[LiteratureRecord], existing_queries: list[str], max_candidates: int = 200) -> list[dict[str, Any]]:
    existing = {query.lower() for query in existing_queries}
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set(existing)
    for record in records:
        text = " ".join([record.title or "", record.abstract or "", " ".join(record.keywords or [])])
        tokens = _tokens(text)
        counts = Counter(tokens)
        high_value = [token for token, _ in counts.most_common(12) if token in IMPORTANT or len(token) > 8]
        for idx in range(max(0, len(high_value) - 1)):
            candidate = f"{high_value[idx]} {high_value[idx + 1]} sleep"
            if len(candidate) < 8 or candidate in seen or candidate in {"sleep brain"}:
                continue
            group = _guess_group(candidate)
            candidates.append(
                {
                    "candidate_query": candidate,
                    "source_paper_id": record.paper_id,
                    "source_terms": ";".join(high_value[:6]),
                    "query_group": group,
                    "expected_mechanism": high_value[idx],
                    "expected_evidence_context": _context(candidate),
                    "priority_score": round(1.0 / (idx + 1), 3),
                    "status": "candidate",
                    "rejection_reason": "",
                }
            )
            seen.add(candidate)
            if len(candidates) >= max_candidates:
                return candidates
    return candidates


def _guess_group(query: str) -> str:
    if any(term in query for term in ["mouse", "rodent", "optogenetic"]):
        return "animal_causal_sleep"
    if any(term in query for term in ["fmri", "mri", "dti"]):
        return "human_sleep_neuroimaging"
    if any(term in query for term in ["gaba", "orexin", "adenosine", "cytokine"]):
        return "molecular_cellular_sleep"
    if "insomnia" in query:
        return "insomnia_clinical_application"
    return "general_sleep_physiology"


def _context(query: str) -> str:
    if any(term in query for term in ["mouse", "rodent", "optogenetic"]):
        return "animal_mechanistic"
    if any(term in query for term in ["fmri", "mri", "dti"]):
        return "human_neuroimaging"
    if any(term in query for term in ["gaba", "orexin", "adenosine"]):
        return "cellular_molecular"
    return "human_general_sleep"


def write_query_expansion_candidates(path: str | Path, candidates: list[dict[str, Any]]) -> None:
    write_csv(Path(path), candidates)

