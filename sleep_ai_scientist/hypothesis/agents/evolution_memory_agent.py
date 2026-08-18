from __future__ import annotations

import re
from typing import Any

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.common.utils import normalize_text
from sleep_ai_scientist.hypothesis.agents.generation_agent import _coerce_list
from sleep_ai_scientist.llm.client import build_llm_client, llm_enabled, load_prompt, normalize_llm_config
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
            f"- {item.title} | Elo={item.elo_rating:.1f} | status={item.status.value} | "
            f"data_testability={_testability_status(item)} | missing_modalities={','.join(_testability_list(item, 'missing_modalities')) or 'none'} | {item.summary}"
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
                "knowledge_context": _truncate_context(knowledge_context or "No knowledge graph context was provided."),
            },
        )
        try:
            return _sanitize_meta_review_report(
                client.call(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=min(max_tokens, int(llm_config.get("meta_review_max_tokens", 1200))),
                    temperature=float(llm_config.get("temperature", 0.2)),
                ).content
            )
        except Exception:
            return _rule_meta_review(registry)

    return _rule_meta_review(registry)


def _rule_meta_review(registry: HypothesisRegistry) -> str:
    counts = registry.count_by_status()
    top = registry.top(3, include_pending=True)
    experiment_top = registry.top_by_experiment_priority(3, include_pending=True)
    lines = [
        "# Hypothesis Meta Review",
        "",
        f"Total hypotheses: {len(registry.all())}",
        f"Status counts: {counts}",
        "",
        "## Scientific Strength Ranking",
    ]
    for index, hypothesis in enumerate(top, start=1):
        lines.append(
            f"{index}. {hypothesis.title} (Elo {hypothesis.elo_rating:.1f}, {hypothesis.status.value}; "
            f"data_testability={_testability_status(hypothesis)})"
        )
        lines.append(f"   - Current-data note: {_testability_note(hypothesis)}")
    lines.append("")
    lines.append("## Current-Data Experiment Priority")
    for index, hypothesis in enumerate(experiment_top, start=1):
        lines.append(
            f"{index}. {hypothesis.title} (experiment_priority={_experiment_priority_score(hypothesis):.1f}; "
            f"data_testability={_testability_status(hypothesis)})"
        )
        missing_modalities = ", ".join(_testability_list(hypothesis, "missing_modalities")) or "none"
        missing_variables = ", ".join(_testability_list(hypothesis, "missing_variables")) or "none"
        lines.append(f"   - Missing modalities: {missing_modalities}; missing variables: {missing_variables}")
    lines.append("")
    lines.append(
        "Recommended next step: treat literature-supported but not-directly-testable mechanisms as data gaps, "
        "not as current experimental evidence."
    )
    return "\n".join(lines)


def _truncate_context(text: str, max_chars: int = 5000) -> str:
    value = str(text or "")
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "\n\n[context truncated for meta-review speed]"


def _sanitize_meta_review_report(report: str) -> str:
    text = str(report or "").strip()
    closing = re.search(r"</think>", text, flags=re.IGNORECASE)
    if closing:
        text = text[closing.end() :].strip()
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    fenced = re.fullmatch(r"```(?:markdown|md)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    first_heading = re.search(r"(?m)^#\s+", text)
    if first_heading:
        text = text[first_heading.start() :].strip()
    return text


def _testability_payload(hypothesis: Hypothesis) -> dict[str, Any]:
    return hypothesis.metadata.get("data_testability", {}) if isinstance(hypothesis.metadata, dict) else {}


def _testability_status(hypothesis: Hypothesis) -> str:
    return str(_testability_payload(hypothesis).get("status", "unknown"))


def _testability_note(hypothesis: Hypothesis) -> str:
    return str(_testability_payload(hypothesis).get("note", "No current-data testability annotation is available."))


def _testability_list(hypothesis: Hypothesis, key: str) -> list[str]:
    value = _testability_payload(hypothesis).get(key, [])
    return [str(item) for item in value] if isinstance(value, list) else []


def _experiment_priority_score(hypothesis: Hypothesis) -> float:
    payload = _testability_payload(hypothesis)
    return float(hypothesis.elo_rating) + float(payload.get("ranking_bonus", 0.0) or 0.0)


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
                ollama_config=state.config.get("_llm_tasks", {}).get("hypothesis_evolution", state.config.get("_selected_llm", {})),
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
            ollama_config=state.config.get("_llm_tasks", {}).get("hypothesis_meta_review", state.config.get("_selected_llm", {})),
            knowledge_context=state.context_blocks.get("knowledge_graph", ""),
        )
        report = _sanitize_meta_review_report(report)
        state.report_path.parent.mkdir(parents=True, exist_ok=True)
        state.report_path.write_text(report, encoding="utf-8")
        write_json(state.output_dir / "hypothesis_reviews.json", [review.model_dump(mode="json") for review in state.registry.reviews])
        write_json(state.output_dir / "tournament_matches.json", [match.model_dump(mode="json") for match in state.registry.matches])
        state.artifacts["report"] = report
        return state
