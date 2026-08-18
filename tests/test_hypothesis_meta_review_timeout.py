from __future__ import annotations

from sleep_ai_scientist.hypothesis.agents import evolution_memory_agent
from sleep_ai_scientist.hypothesis.agents.evolution_memory_agent import synthesize_meta_review
from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.schemas.hypothesis import HypothesisStatus


def test_meta_review_timeout_falls_back_to_rule_report(monkeypatch) -> None:
    registry = HypothesisRegistry(session_id="s")
    registry.add_hypothesis(
        title="Thalamic FC hypothesis",
        summary="Thalamic connectivity relates to insomnia severity.",
        content="content",
        rationale="rationale",
        generation_strategy="test",
        status=HypothesisStatus.active,
    )

    class TimeoutClient:
        provider = "ollama"
        model = "qwen3:14b"

        def call(self, *args, **kwargs):
            raise TimeoutError("timed out")

    monkeypatch.setattr(evolution_memory_agent, "build_llm_client", lambda config: TimeoutClient())

    report = synthesize_meta_review(
        registry,
        ollama_config={"enabled": True, "provider": "ollama", "model": "qwen3:14b"},
        knowledge_context="long context",
    )

    assert "# Hypothesis Meta Review" in report
    assert "Total hypotheses: 1" in report
