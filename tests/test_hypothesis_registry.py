from pathlib import Path

import pytest

from sleep_ai_scientist.common.io import read_json, write_yaml
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline
from sleep_ai_scientist.hypothesis.agents.generation_agent import generate_initial_hypotheses
from sleep_ai_scientist.hypothesis.agents.llm import LLMError
from sleep_ai_scientist.hypothesis.agents.supervisor_agent import select_llm_config
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline
from sleep_ai_scientist.hypothesis.agents.review_agent import reject_near_duplicates, run_reflection
from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.hypothesis.agents.rank_agent import run_pairwise_ranking
from sleep_ai_scientist.hypothesis.agents.memory import (
    ExperimentalFeedback,
    apply_feedback_to_registry,
    build_rlef_injection_block,
    extract_reward_from_feedback,
    promote_feedback_to_reward_memory,
)
from sleep_ai_scientist.hypothesis.agents.tournament import Glicko2State, compute_glicko2_update
from sleep_ai_scientist.schemas.evidence import EvidenceRecord
from sleep_ai_scientist.schemas.hypothesis import HypothesisStatus


OUTPUT_EVIDENCE_PATH = Path("outputs/grounding/evidence_table.json")


def _load_output_evidence() -> list[EvidenceRecord]:
    if not OUTPUT_EVIDENCE_PATH.exists() or OUTPUT_EVIDENCE_PATH.stat().st_size == 0:
        run_grounding_pipeline("configs/grounding_config.yaml")
    return [EvidenceRecord(**row) for row in read_json(OUTPUT_EVIDENCE_PATH)]


def test_hypothesis_registry_generates_reviews_and_outputs(tmp_path):
    registry = generate_initial_hypotheses(_load_output_evidence(), session_id="test_session", max_hypotheses=4)
    assert len(registry.all()) == 4
    assert {item.generation_strategy for item in registry.all()} == {
        "literature_exploration",
        "scientific_debate",
        "assumption_chaining",
        "research_expansion",
    }

    reviews = run_reflection(registry)
    assert len(reviews) == 4
    assert len(registry.active()) == 4
    assert all(item.elo_rating > 1200 for item in registry.active())

    registry.write_outputs(tmp_path, top_k=2)
    assert (tmp_path / "hypothesis_pool.json").exists()
    assert (tmp_path / "hypothesis_registry.csv").exists()
    assert (tmp_path / "top_k_hypotheses.json").exists()
    assert (tmp_path / "hypothesis_lineage.json").exists()


def test_hypothesis_registry_rejects_near_duplicates():
    registry = HypothesisRegistry(session_id="dup_session")
    first = registry.add_hypothesis(
        title="Slow wave generation explains slow wave density alteration",
        summary="slow-wave generation may drive measurable change in slow_wave_density",
        content="A",
        rationale="A",
        generation_strategy="literature_exploration",
        elo_rating=1300,
        status=HypothesisStatus.active,
    )
    second = registry.add_hypothesis(
        title="Slow wave generation explains slow wave density alteration",
        summary="slow-wave generation may drive measurable change in slow_wave_density",
        content="B",
        rationale="B",
        generation_strategy="scientific_debate",
        elo_rating=1200,
        status=HypothesisStatus.active,
    )

    rejected = reject_near_duplicates(registry, duplicate_threshold=0.9)
    assert second.hypothesis_id in rejected
    assert registry.hypotheses[first.hypothesis_id].status == HypothesisStatus.active
    assert registry.hypotheses[second.hypothesis_id].status == HypothesisStatus.rejected


def test_hypothesis_pipeline_writes_expected_artifacts(tmp_path):
    output_dir = tmp_path / "hypotheses"
    report_path = tmp_path / "phase2_hypothesis_report.md"
    config_path = tmp_path / "hypothesis_config.yaml"
    write_yaml(
        config_path,
        {
            "paths": {
                "evidence_table_json": str(OUTPUT_EVIDENCE_PATH),
                "experimental_feedback": str(tmp_path / "experimental_feedback.json"),
                "reward_memory": str(tmp_path / "reward_memory.json"),
                "output_hypotheses_dir": str(output_dir),
                "report_path": str(report_path),
            },
            "hypothesis": {
                "session_id": "tmp_session",
                "max_hypotheses": 4,
                "top_k": 5,
                "duplicate_threshold": 0.92,
                "enable_evolution": True,
            },
            "ollama": {"enabled": False},
        },
    )

    result = run_hypothesis_pipeline(config_path)
    assert result["evidence"] > 0
    assert result["hypotheses"] >= 4
    assert result["agents"] == ["ContextAgent", "GenerationAgent", "ReviewAgent", "RankAgent", "EvolutionMemoryAgent"]
    assert Path(output_dir / "hypothesis_pool.json").exists()
    assert Path(output_dir / "hypothesis_registry.csv").exists()
    assert Path(report_path).exists()


def test_llm_config_defaults_to_online_and_keeps_ollama_option():
    online = select_llm_config({"llm_provider": "online", "online_llm": {"enabled": True, "api_key": "x"}})
    assert online["provider"] == "online"
    assert online["base_url"] == "https://api.deepseek.com"
    assert online["model"] == "deepseek-chat"

    local = select_llm_config({"llm_provider": "ollama", "ollama": {"enabled": False, "model": "llama3.1"}})
    assert local["provider"] == "ollama"
    assert local["base_url"] == "http://localhost:11434"


def test_ollama_generation_raises_when_fallback_disabled():
    with pytest.raises(LLMError):
        generate_initial_hypotheses(
            _load_output_evidence(),
            session_id="ollama_error_session",
            max_hypotheses=1,
            ollama_config={
                "enabled": True,
                "model": "",
                "fallback_to_rules": False,
            },
        )


def test_glicko2_update_changes_rating_rd_and_counts():
    left = Glicko2State(rating=1200, rd=200, volatility=0.06)
    right = Glicko2State(rating=1200, rd=200, volatility=0.06)
    new_left, new_right = compute_glicko2_update(left, right, "A_wins")
    assert new_left.rating > left.rating
    assert new_right.rating < right.rating
    assert new_left.rd < left.rd
    assert new_right.rd < right.rd
    assert new_left.wins == 1
    assert new_right.losses == 1
    assert new_left.matches_played == 1
    assert new_right.matches_played == 1


def test_pairwise_ranking_uses_glicko2_state():
    registry = HypothesisRegistry(session_id="glicko_session")
    left = registry.add_hypothesis(
        title="Higher evidence hypothesis",
        summary="A",
        content="A",
        rationale="A",
        generation_strategy="literature_exploration",
        citations=["p1", "p2"],
        key_assumptions=["a1", "a2"],
        elo_rating=1200,
        rating_deviation=200,
        status=HypothesisStatus.active,
    )
    right = registry.add_hypothesis(
        title="Lower evidence hypothesis",
        summary="B",
        content="B",
        rationale="B",
        generation_strategy="scientific_debate",
        elo_rating=1200,
        rating_deviation=200,
        status=HypothesisStatus.active,
    )
    matches = run_pairwise_ranking(registry)
    assert len(matches) == 1
    assert registry.hypotheses[left.hypothesis_id].elo_rating > 1200
    assert registry.hypotheses[right.hypothesis_id].elo_rating < 1200
    assert registry.hypotheses[left.hypothesis_id].rating_deviation < 200
    assert registry.hypotheses[left.hypothesis_id].wins == 1
    assert registry.hypotheses[right.hypothesis_id].losses == 1


def test_rlef_feedback_updates_glicko_and_prompt_memory():
    registry = HypothesisRegistry(session_id="rlef_session")
    hyp = registry.add_hypothesis(
        title="Feedback target",
        summary="A sleep mechanism hypothesis",
        content="content",
        rationale="rationale",
        generation_strategy="literature_exploration",
        elo_rating=1200,
        rating_deviation=200,
        status=HypothesisStatus.active,
    )
    reward = extract_reward_from_feedback("Experiment validated and strongly supports the mechanism.", 9, 9, 9)
    assert reward > 0.3
    feedback = ExperimentalFeedback(
        feedback_id="fb1",
        hypothesis_id=hyp.hypothesis_id,
        session_id="rlef_session",
        feedback_text="Experiment validated and strongly supports the mechanism.",
        novelty_score=9,
        correctness_score=9,
        testability_score=9,
        computed_reward=reward,
    )
    applied = apply_feedback_to_registry(registry, [feedback])
    assert applied == 1
    assert registry.hypotheses[hyp.hypothesis_id].elo_rating > 1200
    block = build_rlef_injection_block([feedback])
    assert "VALIDATED HYPOTHESES" in block


def test_reward_memory_promotes_strong_feedback_only():
    registry = HypothesisRegistry(session_id="memory_session")
    hyp = registry.add_hypothesis(
        title="Memory target",
        summary="Mechanistic sleep feedback target",
        content="content",
        rationale="rationale",
        generation_strategy="literature_exploration",
        status=HypothesisStatus.active,
    )
    feedback = ExperimentalFeedback(
        feedback_id="fb_memory",
        hypothesis_id=hyp.hypothesis_id,
        session_id="memory_session",
        feedback_text="Validated pathway reduces insomnia severity and supports the mechanism.",
        computed_reward=0.8,
    )
    memory = promote_feedback_to_reward_memory([feedback], registry, [])
    assert len(memory) == 1
    assert memory[0].computed_reward == 0.8
    assert "validated" in memory[0].mechanistic_keywords
