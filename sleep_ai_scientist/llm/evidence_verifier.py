from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import ensure_parent
from sleep_ai_scientist.llm.json_parser import parse_json_object
from sleep_ai_scientist.llm.prompt_templates import EVIDENCE_VERIFICATION_PROMPT
from sleep_ai_scientist.llm.safety import validate_verified_claim
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord, EvidenceType


class EvidenceVerifier:
    """Optional LLM verifier that can revise rule evidence without creating unsupported evidence."""

    def __init__(self, client: Any | None = None, log_file: str | Path | None = None, excluded_log_file: str | Path | None = None, fail_open: bool = True):
        self.client = client
        self.log_file = Path(log_file) if log_file else None
        self.excluded_log_file = Path(excluded_log_file) if excluded_log_file else None
        self.fail_open = fail_open
        self.calls_attempted = 0
        self.calls_succeeded = 0
        self.calls_failed = 0
        self.revised_evidence_count = 0
        self.split_claim_count = 0
        self.excluded_claim_count = 0

    def should_verify(self, record: EvidenceRecord) -> bool:
        score = record.extraction_confidence_score if record.extraction_confidence_score is not None else record.confidence_score
        text = (record.source_text or "").lower()
        return (
            record.direction == EvidenceDirection.unclear
            or 0.35 <= (score or 0.0) <= 0.70
            or any(term in text for term in ["no significant", "no association", "no difference", "confound", "limitation"])
        )

    def verify(self, records: list[EvidenceRecord], rules: dict[str, Any] | None = None) -> list[EvidenceRecord]:
        if not self.client:
            return records
        verified: list[EvidenceRecord] = []
        for record in records:
            if not self.should_verify(record):
                verified.append(record)
                continue
            try:
                self.calls_attempted += 1
                prompt = EVIDENCE_VERIFICATION_PROMPT.format(source_text=record.source_text, candidate_json=json.dumps(record.model_dump(mode="json"), ensure_ascii=False))
                payload = parse_json_object(self.client.complete(prompt))
                claims = payload.get("verified_claims", [])
                self.calls_succeeded += 1
            except Exception as exc:
                self.calls_failed += 1
                record.llm_warnings.append(str(exc))
                if not self.fail_open:
                    raise
                verified.append(record)
                continue
            included = 0
            for claim in claims:
                if not claim.get("should_include", True):
                    self._exclude(record, claim, ["should_include_false"])
                    continue
                errors = validate_verified_claim(claim, record.source_text or "")
                if errors:
                    self._exclude(record, claim, errors)
                    continue
                revised = record.model_copy(deep=True) if hasattr(record, "model_copy") else EvidenceRecord(**record.model_dump())
                revised.claim = str(claim.get("claim") or revised.claim)
                revised.mechanism = str(claim.get("mechanism") or revised.mechanism)
                revised.population = str(claim.get("population") or revised.population)
                revised.condition = claim.get("condition") or revised.condition
                revised.comparison_group = claim.get("comparison_group") or revised.comparison_group
                revised.modality = str(claim.get("modality") or revised.modality)
                revised.variable_or_feature = str(claim.get("variable_or_feature") or revised.variable_or_feature)
                revised.direction = EvidenceDirection(claim.get("direction"))
                revised.effect_direction = claim.get("effect_direction") or revised.effect_direction
                revised.evidence_type = EvidenceType(claim.get("evidence_type"))
                revised.study_design = claim.get("study_design") or revised.study_design
                revised.sample_size_total = claim.get("sample_size_total") or revised.sample_size_total
                revised.species = claim.get("species") or revised.species
                revised.limitations = claim.get("limitations") or revised.limitations
                revised.confounds = claim.get("confounds") or revised.confounds
                revised.statistical_note = claim.get("statistical_note") or revised.statistical_note
                revised.confidence_reason = claim.get("confidence_reason") or revised.confidence_reason
                revised.llm_verified = True
                revised.llm_revision_applied = revised.model_dump(mode="json") != record.model_dump(mode="json")
                revised.llm_warnings = claim.get("warnings") or []
                if revised.llm_revision_applied:
                    self.revised_evidence_count += 1
                verified.append(revised)
                included += 1
            if included > 1:
                self.split_claim_count += included - 1
            if included == 0:
                verified.append(record)
            self._log(record, claims)
        return verified

    def _log(self, record: EvidenceRecord, claims: list[dict[str, Any]]) -> None:
        if not self.log_file:
            return
        ensure_parent(self.log_file)
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"evidence_id": record.evidence_id, "claim_count": len(claims)}, ensure_ascii=False) + "\n")

    def _exclude(self, record: EvidenceRecord, claim: dict[str, Any], errors: list[str]) -> None:
        self.excluded_claim_count += 1
        if not self.excluded_log_file:
            return
        ensure_parent(self.excluded_log_file)
        with self.excluded_log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"evidence_id": record.evidence_id, "claim": claim, "errors": errors}, ensure_ascii=False) + "\n")
