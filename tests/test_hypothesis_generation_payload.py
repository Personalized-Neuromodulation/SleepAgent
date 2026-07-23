from sleep_ai_scientist.hypothesis.agents.generation_agent import _coerce_hypothesis_payload, _generate_with_llm, _missing_required_fields
from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord
from sleep_ai_scientist.schemas.hypothesis import GenerationStrategy


def test_coerce_hypothesis_payload_unwraps_response_object():
    payload = _coerce_hypothesis_payload(
        {
            "response": {
                "title": "Thalamocortical insomnia hypothesis",
                "summary": "A compact summary.",
                "content": "A full hypothesis statement.",
                "rationale": "A grounded rationale.",
                "experimental_plan": "Run fMRI and EEG tests.",
            }
        }
    )

    assert payload["title"] == "Thalamocortical insomnia hypothesis"
    assert payload["summary"] == "A compact summary."
    assert payload["content"] == "A full hypothesis statement."
    assert payload["rationale"] == "A grounded rationale."
    assert _missing_required_fields(payload) == []


def test_scientific_debate_generation_uses_one_strict_json_call(monkeypatch):
    calls = []

    class FakeClient:
        provider = "fake"
        model = "fake-model"

        def call(self, *_args, **_kwargs):
            raise AssertionError("scientific_debate must not use a natural-language first turn")

        def call_json(self, messages, *, max_tokens=8192, temperature=None):
            calls.append({"messages": messages, "max_tokens": max_tokens, "temperature": temperature})
            return {
                "title": "Debated thalamocortical insomnia hypothesis",
                "summary": "A strict JSON summary.",
                "content": "A strict JSON hypothesis statement.",
                "rationale": "A strict JSON rationale grounded in evidence.",
                "experimental_plan": "Test approved EEG/fMRI features.",
                "debate_critique": "Scientist B noted limited causal evidence and possible confounds.",
                "debate_refinement": "Scientist A narrowed the hypothesis to a falsifiable EEG/fMRI prediction.",
            }

    monkeypatch.setattr("sleep_ai_scientist.hypothesis.agents.generation_agent.build_llm_client", lambda _config: FakeClient())
    registry = HypothesisRegistry(session_id="test_session")
    evidence = [
        EvidenceRecord(
            evidence_id="E1",
            paper_id="P1",
            claim="Insomnia alters thalamocortical slow-wave coupling.",
            population="insomnia",
            modality="EEG/fMRI",
            variable_or_feature="slow wave density",
            mechanism="thalamocortical coupling",
            direction=EvidenceDirection.support,
            evidence_quality_score=0.9,
        )
    ]

    hypothesis = _generate_with_llm(
        evidence,
        session_id="test_session",
        strategy=GenerationStrategy.scientific_debate.value,
        round_number=1,
        registry=registry,
        llm_config={"enabled": True, "provider": "ollama", "model": "fake-model"},
    )

    assert hypothesis is not None
    assert hypothesis.title == "Debated thalamocortical insomnia hypothesis"
    assert hypothesis.metadata["debate_critique"] == "Scientist B noted limited causal evidence and possible confounds."
    assert hypothesis.metadata["debate_refinement"] == "Scientist A narrowed the hypothesis to a falsifiable EEG/fMRI prediction."
    assert len(calls) == 1
    assert len(calls[0]["messages"]) == 2
    prompt = calls[0]["messages"][1]["content"]
    assert "Scientist B" in prompt
    assert "Return only one valid JSON object" in prompt
    assert '"title"' in prompt and '"summary"' in prompt and '"content"' in prompt and '"rationale"' in prompt
    assert '"debate_critique"' in prompt
    assert '"debate_refinement"' in prompt
