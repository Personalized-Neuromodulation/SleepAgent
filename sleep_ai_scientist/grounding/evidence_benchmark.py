from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_csv, write_json
from sleep_ai_scientist.schemas.evidence import EvidenceRecord
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def _accuracy(expected: list[str], observed: list[str]) -> float:
    if not expected:
        return 0.0
    return round(sum(1 for exp, obs in zip(expected, observed) if exp == obs) / len(expected), 3)


def run_evidence_benchmark(
    evidence: list[EvidenceRecord],
    gold_evidence_path: str | Path,
    out_path: str | Path,
    mode: str = "rule_only",
) -> dict[str, Any]:
    path = Path(gold_evidence_path)
    if not path.exists():
        return {}
    gold = read_csv(path)
    by_paper = {}
    for item in evidence:
        by_paper.setdefault(item.paper_id, []).append(item)
    expected_mechanisms = [row.get("expected_mechanism", "") for row in gold]
    matched = []
    for row in gold:
        candidates = by_paper.get(row.get("paper_id", ""), [])
        hit = next((item for item in candidates if item.mechanism == row.get("expected_mechanism")), candidates[0] if candidates else None)
        matched.append(hit)
    observed_mechanisms = [item.mechanism if item else "" for item in matched]
    mechanism_tp = sum(1 for exp, obs in zip(expected_mechanisms, observed_mechanisms) if exp == obs)
    mechanism_precision = round(mechanism_tp / max(1, len([item for item in evidence if item.mechanism in expected_mechanisms])), 3)
    mechanism_recall = round(mechanism_tp / max(1, len(gold)), 3)
    result = {
        "mode": mode,
        "mechanism_recall": mechanism_recall,
        "mechanism_precision": mechanism_precision,
        "direction_accuracy": _accuracy([row.get("expected_direction", "") for row in gold], [item.direction.value if item else "" for item in matched]),
        "modality_accuracy": _accuracy([row.get("expected_modality", "") for row in gold], [item.modality if item else "" for item in matched]),
        "variable_match_rate": _accuracy([row.get("expected_variable_or_feature", "") for row in gold], [item.variable_or_feature if item else "" for item in matched]),
        "species_accuracy": _accuracy([row.get("expected_species", "") for row in gold], [item.species if item else "" for item in matched]),
        "evidence_context_accuracy": _accuracy([row.get("expected_evidence_context", "") for row in gold], [item.evidence_context if item else "" for item in matched]),
        "downstream_role_accuracy": _accuracy([row.get("expected_downstream_role", "") for row in gold], [item.downstream_role if item else "" for item in matched]),
        "paper_coverage": round(sum(1 for item in matched if item is not None) / max(1, len(gold)), 3),
        "macro_f1_simple": round((2 * mechanism_precision * mechanism_recall) / max(0.001, mechanism_precision + mechanism_recall), 3),
        "hallucinated_evidence_count": sum(1 for item in evidence if not item.source_text),
    }
    write_json(Path(out_path), result)
    return result
