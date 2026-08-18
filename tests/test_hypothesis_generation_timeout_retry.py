from __future__ import annotations

from sleep_ai_scientist.hypothesis.agents import generation_agent
from sleep_ai_scientist.hypothesis.agents.generation_agent import generate_hypothesis_from_evidence
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord


def test_generation_compacts_context_before_first_llm_call(monkeypatch) -> None:
    calls: list[int] = []

    class SuccessClient:
        provider = "ollama"
        model = "qwen3:14b"

        def call_json(self, messages, *, max_tokens, temperature):
            calls.append(sum(len(item.get("content", "")) for item in messages))
            return _payload("Precompact hypothesis")

    monkeypatch.setattr(generation_agent, "build_llm_client", lambda config: SuccessClient())

    hypothesis = generate_hypothesis_from_evidence(
        [_evidence()],
        session_id="s",
        strategy="literature_exploration",
        ollama_config={"enabled": True, "provider": "ollama", "model": "qwen3:14b"},
        knowledge_context="long context " * 2000,
        prior_context="prior context " * 500,
        rlef_context="feedback context " * 500,
    )

    assert hypothesis is not None
    assert hypothesis.title == "Precompact hypothesis"
    assert len(calls) == 1
    assert calls[0] < 12000


def test_generation_timeout_retries_with_compact_context(monkeypatch) -> None:
    calls: list[int] = []

    class TimeoutThenSuccessClient:
        provider = "ollama"
        model = "qwen3:14b"

        def call_json(self, messages, *, max_tokens, temperature):
            calls.append(sum(len(item.get("content", "")) for item in messages))
            if len(calls) == 1:
                raise TimeoutError("timed out")
            return _payload("Compact retry hypothesis")

    monkeypatch.setattr(generation_agent, "build_llm_client", lambda config: TimeoutThenSuccessClient())

    hypothesis = generate_hypothesis_from_evidence(
        [_evidence()],
        session_id="s",
        strategy="literature_exploration",
        ollama_config={"enabled": True, "provider": "ollama", "model": "qwen3:14b"},
        knowledge_context="long context " * 2000,
        prior_context="prior context " * 500,
        rlef_context="feedback context " * 500,
    )

    assert hypothesis is not None
    assert hypothesis.title == "Compact retry hypothesis"
    assert len(calls) == 2
    assert calls[0] < 12000
    assert calls[1] <= calls[0]


def _payload(title: str) -> dict[str, object]:
    return {
        "title": title,
        "summary": "A compact retry can still generate a grounded hypothesis.",
        "content": "DMN-SN FC may track insomnia severity.",
        "rationale": "The selected evidence links fMRI FC with sleep severity.",
        "experimental_plan": "Test FC against ISI and PSQI.",
        "novelty_assessment": "Uses locked network candidates.",
        "key_assumptions": ["FC is measurable"],
        "citations": ["paper_1"],
    }


def _evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="e1",
        paper_id="paper_1",
        claim="DMN and salience network connectivity is associated with insomnia severity.",
        population="insomnia",
        modality="fMRI",
        variable_or_feature="DMN_salience_FC",
        mechanism="network switching",
        direction=EvidenceDirection.support,
        confidence_score=0.9,
        evidence_quality_score=0.9,
    )
