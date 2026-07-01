from __future__ import annotations

from typing import Any

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.common.utils import normalize_text
from sleep_ai_scientist.hypothesis.agents.generation_agent import _coerce_list
from sleep_ai_scientist.hypothesis.agents.llm import build_llm_client, llm_enabled, load_prompt, normalize_llm_config
from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.hypothesis.agents.state import HypothesisSessionState
from sleep_ai_scientist.hypothesis.agents.memory import apply_feedback_to_registry, promote_feedback_to_reward_memory, write_reward_memory
from sleep_ai_scientist.schemas.hypothesis import Hypothesis, HypothesisStatus


EVOLUTION_STRATEGIES = ["grounding", "coherence", "cross_pollination", "combination", "simplification", "out_of_box"]


def _llm_evolve(
    registry: HypothesisRegistry,
    parents: list[Hypothesis],
    strategy: str,
    round_number: int,
    ollama_config: dict[str, Any],
    rlef_context: str = "",
    knowledge_context: str = "",
) -> Hypothesis:
    llm_config = normalize_llm_config(ollama_config)
    client = build_llm_client(llm_config)
    parent_text = "\n\n".join(
        f"[P{index}] id={item.hypothesis_id}\nTitle: {item.title}\nSummary: {item.summary}\nRationale: {item.rationale}\nPlan: {item.experimental_plan}"
        for index, item in enumerate(parents, start=1)
    )
    system, prompt, max_tokens = load_prompt(
        "evolution",
        "evolve",
        {
            "strategy": strategy,
            "parent_text": parent_text,
            "rlef_context": rlef_context,
            "knowledge_context": knowledge_context or "No knowledge graph context was provided.",
        },
    )
    payload = client.call_json(
        [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=float(llm_config.get("temperature", 0.2)),
    )
    primary = parents[0]
    return registry.add_hypothesis(
        title=normalize_text(payload.get("title", "")),
        summary=normalize_text(payload.get("summary", "")),
        content=normalize_text(payload.get("content", "")),
        rationale=normalize_text(payload.get("rationale", "")),
        experimental_plan=normalize_text(payload.get("experimental_plan") or payload.get("experimentalPlan")),
        novelty_assessment=normalize_text(payload.get("novelty_assessment") or payload.get("noveltyAssessment")),
        key_assumptions=_coerce_list(payload.get("key_assumptions") or payload.get("keyAssumptions")),
        citations=_coerce_list(payload.get("citations")),
        parent_ids=[item.hypothesis_id for item in parents],
        generation_strategy=f"evolution:{strategy}",
        generation_round=round_number,
        elo_rating=round(primary.elo_rating * 0.85, 2),
        status=HypothesisStatus.pending_review,
        metadata={"evolved_from": [item.hypothesis_id for item in parents], "llm_provider": client.provider, "llm_model": client.model},
    )


def evolve_top_hypothesis(
    registry: HypothesisRegistry,
    round_number: int = 0,
    strategy: str | None = None,
    ollama_config: dict[str, Any] | None = None,
    rlef_context: str = "",
    knowledge_context: str = "",
) -> Hypothesis | None:
    parents = registry.top(3)
    if not parents:
        return None
    strategy = strategy or EVOLUTION_STRATEGIES[round_number % len(EVOLUTION_STRATEGIES)]
    if llm_enabled(ollama_config):
        return _llm_evolve(
            registry,
            parents,
            strategy,
            round_number,
            ollama_config,
            rlef_context=rlef_context,
            knowledge_context=knowledge_context,
        )
    primary = parents[0]
    parent_ids = [primary.hypothesis_id]
    if strategy == "combination" and len(parents) > 1:
        parent_ids = [item.hypothesis_id for item in parents]
        title = f"Combined mechanism: {parents[0].title}"
        summary = f"Combines {len(parents)} ranked hypotheses into a broader multimodal mechanism."
    elif strategy == "simplification":
        title = f"Simplified test of {primary.title}"
        summary = f"Reduces {primary.title} to its most measurable prediction."
    else:
        title = f"Evolved {strategy} variant of {primary.title}"
        summary = f"Refines {primary.summary}"

    return registry.add_hypothesis(
        title=title,
        summary=summary,
        content=f"{primary.content} Evolution strategy '{strategy}' emphasizes stronger grounding and clearer tests.",
        rationale=f"Derived from parent hypothesis {primary.hypothesis_id} to improve {strategy}.",
        experimental_plan=primary.experimental_plan,
        novelty_assessment=f"Evolved through {strategy} from a high-ranked parent.",
        key_assumptions=primary.key_assumptions,
        citations=primary.citations,
        parent_ids=parent_ids,
        generation_strategy=f"evolution:{strategy}",
        generation_round=round_number,
        elo_rating=round(primary.elo_rating * 0.85, 2),
        status=HypothesisStatus.pending_review,
        metadata={"evolved_from": parent_ids},
    )


def synthesize_meta_review(
    registry: HypothesisRegistry,
    ollama_config: dict[str, Any] | None = None,
    knowledge_context: str = "",
) -> str:
    if llm_enabled(ollama_config):
        llm_config = normalize_llm_config(ollama_config)
        client = build_llm_client(llm_config)
        hypotheses = "\n".join(
            f"- {item.title} | Elo={item.elo_rating:.1f} | status={item.status.value} | {item.summary}"
            for item in registry.top(10, include_pending=True)
        )
        reviews = "\n".join(
            f"- {item.review_type.value} {item.verdict.value}: {item.summary}"
            for item in registry.reviews[-20:]
        )
        system, prompt, max_tokens = load_prompt(
            "meta_review",
            "synthesis",
            {
                "hypotheses": hypotheses,
                "reviews": reviews,
                "knowledge_context": knowledge_context or "No knowledge graph context was provided.",
            },
        )
        return client.call(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=float(llm_config.get("temperature", 0.2)),
        ).content

    counts = registry.count_by_status()
    top = registry.top(3, include_pending=True)
    lines = [
        "# Hypothesis Meta Review",
        "",
        f"Total hypotheses: {len(registry.all())}",
        f"Status counts: {counts}",
        "",
        "Top hypotheses:",
    ]
    for index, hypothesis in enumerate(top, start=1):
        lines.append(f"{index}. {hypothesis.title} (Elo {hypothesis.elo_rating:.1f}, {hypothesis.status.value})")
    lines.append("")
    lines.append("Recommended next step: review pending hypotheses, reject near-duplicates, then rank active candidates.")
    return "\n".join(lines)


class EvolutionMemoryAgent:
    name = "EvolutionMemoryAgent"

    def run(self, state: HypothesisSessionState) -> HypothesisSessionState:
        hypothesis_cfg = state.config.get("hypothesis", {})
        state.artifacts["feedback_updates"] = apply_feedback_to_registry(state.registry, state.experimental_feedback)
        updated_reward_memory = promote_feedback_to_reward_memory(
            state.experimental_feedback,
            state.registry,
            state.reward_memory,
        )
        state.artifacts["reward_memory_updated"] = updated_reward_memory != state.reward_memory
        state.reward_memory = updated_reward_memory

        if bool(hypothesis_cfg.get("enable_evolution", True)):
            evolved = evolve_top_hypothesis(
                state.registry,
                round_number=int(state.artifacts.get("evolution_round", 1)) + 1,
                ollama_config=state.config.get("_selected_llm", {}),
                rlef_context=state.context_blocks.get("rlef_context", ""),
                knowledge_context=state.context_blocks.get("knowledge_graph", ""),
            )
            state.artifacts["evolved_hypothesis_id"] = evolved.hypothesis_id if evolved is not None else ""
            state.artifacts["evolution_round"] = int(state.artifacts.get("evolution_round", 1)) + 1
        return state

    def write_outputs(self, state: HypothesisSessionState) -> HypothesisSessionState:
        if state.output_dir is None or state.report_path is None:
            raise ValueError("Missing output_dir or report_path in hypothesis session state")
        reward_memory_path = state.artifacts.get("reward_memory_path")
        if reward_memory_path and state.artifacts.get("reward_memory_updated"):
            write_reward_memory(reward_memory_path, state.reward_memory)
        top_k = int(state.config.get("hypothesis", {}).get("top_k", 5))
        state.registry.write_outputs(state.output_dir, top_k=top_k)
        report = synthesize_meta_review(
            state.registry,
            ollama_config=state.config.get("_selected_llm", {}),
            knowledge_context=state.context_blocks.get("knowledge_graph", ""),
        )
        state.report_path.parent.mkdir(parents=True, exist_ok=True)
        state.report_path.write_text(report, encoding="utf-8")
        write_json(state.output_dir / "hypothesis_reviews.json", [review.model_dump(mode="json") for review in state.registry.reviews])
        write_json(state.output_dir / "tournament_matches.json", [match.model_dump(mode="json") for match in state.registry.matches])
        state.artifacts["report"] = report
        return state
