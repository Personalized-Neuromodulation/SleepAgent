from __future__ import annotations

from typing import Any

from sleep_ai_scientist.benchmark.utils import analysis_ready_variables, evidence_ids, load_hypotheses, model_dump_rows, output_path, input_path
from sleep_ai_scientist.common.io import read_yaml, write_csv
from sleep_ai_scientist.schemas.benchmark import GroundingBenchmarkScore


def score_grounding(hypothesis: dict[str, Any], ready: set[str], valid_evidence: set[str], mapping: dict[str, Any]) -> GroundingBenchmarkScore:
    variables = hypothesis.get("variables") or {}
    used = hypothesis.get("used_data_features") or variables.get("independent", []) + variables.get("dependent", []) + variables.get("covariates", [])
    missing = [name for name in used if name not in ready]
    evidence = [eid for eid in hypothesis.get("supporting_evidence_ids", []) if eid in valid_evidence]
    mappings = mapping.get("mappings", [])
    mechanism = hypothesis.get("mechanism")
    mapped = [item.get("concept") for item in mappings if item.get("concept") == mechanism and item.get("mapping_status") != "unavailable"]
    unavailable = [item.get("concept") for item in mappings if item.get("concept") == mechanism and item.get("mapping_status") == "unavailable"]
    data_score = 0.0 if missing else 1.0
    evidence_score = min(1.0, len(evidence) / max(1, len(hypothesis.get("supporting_evidence_ids", [])))) if hypothesis.get("supporting_evidence_ids") else 0.0
    warnings = []
    if missing:
        warnings.append("missing_variables")
    if not evidence:
        warnings.append("missing_valid_evidence")
    if unavailable:
        warnings.append("mechanism_unavailable_in_mapping")
    return GroundingBenchmarkScore(
        hypothesis_id=hypothesis.get("hypothesis_id", ""),
        used_variables=used,
        missing_variables=missing,
        mapped_concepts=[item for item in mapped if item],
        unavailable_concepts=[item for item in unavailable if item],
        evidence_ids=evidence,
        data_grounding_score=data_score,
        evidence_grounding_score=round(evidence_score, 4),
        grounding_passed=not missing,
        warnings=warnings,
    )


def run_grounding_benchmark(config: dict[str, Any]) -> list[GroundingBenchmarkScore]:
    mapping_path = input_path(config, "evidence_to_variable_map")
    mapping = read_yaml(mapping_path) if mapping_path.exists() else {}
    scores = [score_grounding(item, analysis_ready_variables(config), evidence_ids(config), mapping) for item in load_hypotheses(config)]
    write_csv(output_path(config, "grounding_benchmark_scores"), model_dump_rows(scores))
    return scores
