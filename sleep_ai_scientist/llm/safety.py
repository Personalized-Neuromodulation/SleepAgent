from __future__ import annotations

from typing import Any

from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceType


def validate_verified_claim(claim: dict[str, Any], source_text: str, *, max_claim_length: int = 600) -> list[str]:
    """Return safety errors for an LLM verified claim."""
    errors: list[str] = []
    if not source_text:
        errors.append("missing_source_text")
    if not claim.get("claim"):
        errors.append("missing_claim")
    if len(str(claim.get("claim", ""))) > max_claim_length:
        errors.append("claim_too_long")
    if claim.get("direction") not in {item.value for item in EvidenceDirection}:
        errors.append("invalid_direction")
    if claim.get("evidence_type") not in {item.value for item in EvidenceType}:
        errors.append("invalid_evidence_type")
    if not claim.get("mechanism"):
        errors.append("missing_mechanism")
    claim_text = str(claim.get("claim", "")).lower()
    source_lower = source_text.lower()
    token_overlap = [token for token in claim_text.split() if len(token) > 4 and token in source_lower]
    if claim_text and not token_overlap:
        errors.append("claim_not_supported_by_source_text")
    return errors
