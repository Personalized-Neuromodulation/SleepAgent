from __future__ import annotations

from typing import Any


def compile_grounding_validation_spec(
    hypothesis: dict[str, Any],
    *,
    selected_rank: int | None = None,
) -> dict[str, Any]:
    """Compile a selected grounding hypothesis into a locked validation spec."""
    source = str(hypothesis.get("source", "")).strip().lower()
    if source != "grounding":
        raise ValueError("Validation spec inputs must have source='grounding'.")

    candidate_fc = _string_list(hypothesis.get("candidate_fc"))
    if not candidate_fc:
        raise ValueError("Grounding validation spec requires non-empty candidate_fc.")

    evidence_ids = _string_list(hypothesis.get("evidence_ids"))
    if not evidence_ids:
        raise ValueError("Grounding validation spec requires non-empty evidence_ids.")

    expected_direction = hypothesis.get("expected_direction") or {}
    if not isinstance(expected_direction, dict):
        raise ValueError("expected_direction must be a mapping from FC feature to direction.")

    spec: dict[str, Any] = {
        "source": "grounding",
        "locked": True,
        "selected_rank": selected_rank,
        "hypothesis_id": str(hypothesis.get("hypothesis_id", "")),
        "hypothesis": str(hypothesis.get("hypothesis", "")),
        "evidence_ids": evidence_ids,
        "candidate_fc": candidate_fc,
        "expected_direction": {str(key): str(value) for key, value in expected_direction.items()},
        "clinical_anchors": _string_list(hypothesis.get("clinical_anchors")),
        "validation_policy": {
            "local_data_role": "confirmatory_validation_only",
            "healthy_label_rule": "subject starts with sub-YZHC",
            "feature_selection": "candidate_fc must be prespecified by grounding before local outcome testing",
        },
    }
    return spec


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value if str(item)]
