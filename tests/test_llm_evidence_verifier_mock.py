import json

from sleep_ai_scientist.llm.evidence_verifier import EvidenceVerifier
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord


class MockClient:
    def complete(self, prompt: str) -> str:
        return json.dumps(
            {
                "verified_claims": [
                    {
                        "claim": "Spindle density showed no significant association.",
                        "mechanism": "spindle generation",
                        "population": "insomnia",
                        "condition": "insomnia",
                        "comparison_group": "control",
                        "modality": "EEG",
                        "variable_or_feature": "spindle_density",
                        "direction": "null",
                        "effect_direction": "no_difference",
                        "evidence_type": "empirical",
                        "study_design": "observational",
                        "sample_size_total": None,
                        "species": "human",
                        "limitations": [],
                        "confounds": [],
                        "statistical_note": None,
                        "confidence_reason": "negation in source",
                        "should_include": True,
                        "warnings": [],
                    }
                ]
            }
        )


def test_llm_mock_can_revise_direction():
    record = EvidenceRecord(evidence_id="e1", paper_id="p1", claim="claim", source_text="Spindle density showed no significant association.", mechanism="spindle generation", direction=EvidenceDirection.unclear)
    verified = EvidenceVerifier(MockClient()).verify([record])
    assert verified[0].direction == EvidenceDirection.null
    assert verified[0].llm_verified is True
