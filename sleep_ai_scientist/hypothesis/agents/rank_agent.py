from __future__ import annotations

from typing import Any

from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.hypothesis.agents.llm import build_llm_client, llm_enabled, load_prompt, normalize_llm_config
from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.hypothesis.agents.state import HypothesisSessionState
from sleep_ai_scientist.hypothesis.agents.tournament import Glicko2State, compute_glicko2_update
from sleep_ai_scientist.schemas.hypothesis import Hypothesis, TournamentMatch


def compare_hypotheses(left: Hypothesis, right: Hypothesis) -> str:
    left_score = left.elo_rating + 5 * len(left.citations) + 2 * len(left.key_assumptions)
    right_score = right.elo_rating + 5 * len(right.citations) + 2 * len(right.key_assumptions)
    if abs(left_score - right_score) < 1e-6:
        return "draw"
    return "A_wins" if left_score > right_score else "B_wins"


def _result_from_winner(value: Any) -> str:
    winner = str(value or "draw").strip().upper()
    if winner in {"A", "A_WINS"}:
        return "A_wins"
    if winner in {"B", "B_WINS"}:
        return "B_wins"
    return "draw"


def _simple_match(left: Hypothesis, right: Hypothesis, ollama_config: dict[str, Any], knowledge_context: str = "") -> tuple[str, str]:
    llm_config = normalize_llm_config(ollama_config)
    client = build_llm_client(llm_config)
    system, prompt, max_tokens = load_prompt(
        "ranking",
        "simple_comparison",
        {
            "title_a": left.title,
            "summary_a": left.summary,
            "rationale_a": left.rationale,
            "citations_a": left.citations,
            "title_b": right.title,
            "summary_b": right.summary,
            "rationale_b": right.rationale,
            "citations_b": right.citations,
            "knowledge_context": knowledge_context or "No knowledge graph context was provided.",
        },
    )
    payload = client.call_json(
        [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=float(llm_config.get("temperature", 0.2)),
    )
    return _result_from_winner(payload.get("winner")), str(payload.get("rationale", ""))


def _debate_match(left: Hypothesis, right: Hypothesis, ollama_config: dict[str, Any], knowledge_context: str = "") -> tuple[str, str]:
    llm_config = normalize_llm_config(ollama_config)
    client = build_llm_client(llm_config)
    temperature = float(llm_config.get("temperature", 0.2))
    system, base_prompt, max_tokens = load_prompt(
        "ranking",
        "debate_match",
        {
            "title_a": left.title,
            "summary_a": left.summary,
            "rationale_a": left.rationale,
            "title_b": right.title,
            "summary_b": right.summary,
            "rationale_b": right.rationale,
            "knowledge_context": knowledge_context or "No knowledge graph context was provided.",
        },
    )
    advocacy = client.call(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": base_prompt + "\n\nRound 1: advocate the strongest case for both hypotheses."},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    ).content
    cross = client.call(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": base_prompt + "\n\nRound 1: advocate the strongest case for both hypotheses."},
            {"role": "assistant", "content": advocacy},
            {
                "role": "user",
                "content": "Round 2: cross-examine both hypotheses. Focus on novelty flaws, weak assumptions, and testability.",
            },
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    ).content
    payload = client.call_json(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": base_prompt + "\n\nRound 1: advocate the strongest case for both hypotheses."},
            {"role": "assistant", "content": advocacy},
            {"role": "user", "content": "Round 2: cross-examine both hypotheses."},
            {"role": "assistant", "content": cross},
            {
                "role": "user",
                "content": 'Final judgment. Return JSON: {"winner": "A|B|draw", "rationale": "detailed explanation"}',
            },
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    rationale = f"[Advocacy]\n{advocacy}\n\n[Cross-examination]\n{cross}\n\n[Judgment]\n{payload.get('rationale', '')}"
    return _result_from_winner(payload.get("winner")), rationale


def run_pairwise_ranking(
    registry: HypothesisRegistry,
    round_number: int = 0,
    ollama_config: dict[str, Any] | None = None,
    knowledge_context: str = "",
) -> list[TournamentMatch]:
    active = registry.top(20)
    matches: list[TournamentMatch] = []
    for index, left in enumerate(active):
        for right in active[index + 1 :]:
            if llm_enabled(ollama_config):
                avg_rating = (left.elo_rating + right.elo_rating) / 2
                if avg_rating >= float(normalize_llm_config(ollama_config).get("debate_rating_threshold", 1400)):
                    result, rationale = _debate_match(left, right, ollama_config, knowledge_context=knowledge_context)
                else:
                    result, rationale = _simple_match(left, right, ollama_config, knowledge_context=knowledge_context)
            else:
                result = compare_hypotheses(left, right)
                rationale = "Rule-based local tournament comparison."

            new_left, new_right = compute_glicko2_update(_state(left), _state(right), result)
            registry.update_rating(
                left.hypothesis_id,
                new_left.rating,
                rating_deviation=new_left.rd,
                volatility=new_left.volatility,
                matches_played=new_left.matches_played,
                wins=new_left.wins,
                losses=new_left.losses,
                draws=new_left.draws,
            )
            registry.update_rating(
                right.hypothesis_id,
                new_right.rating,
                rating_deviation=new_right.rd,
                volatility=new_right.volatility,
                matches_played=new_right.matches_played,
                wins=new_right.wins,
                losses=new_right.losses,
                draws=new_right.draws,
            )

            fresh_left = registry.hypotheses[left.hypothesis_id]
            fresh_right = registry.hypotheses[right.hypothesis_id]
            match = TournamentMatch(
                match_id=stable_id("match", left.hypothesis_id, right.hypothesis_id, round_number),
                session_id=registry.session_id,
                hypothesis_a_id=left.hypothesis_id,
                hypothesis_b_id=right.hypothesis_id,
                result=result,
                winner_elo_after=max(fresh_left.elo_rating, fresh_right.elo_rating),
                loser_elo_after=min(fresh_left.elo_rating, fresh_right.elo_rating),
                rationale=rationale,
                round=round_number,
            )
            registry.add_match(match)
            matches.append(match)
    return matches


def _state(hypothesis: Hypothesis) -> Glicko2State:
    return Glicko2State(
        rating=hypothesis.elo_rating,
        rd=hypothesis.rating_deviation,
        volatility=hypothesis.volatility,
        matches_played=hypothesis.matches_played,
        wins=hypothesis.wins,
        losses=hypothesis.losses,
        draws=hypothesis.draws,
    )


class RankAgent:
    name = "RankAgent"

    def run(self, state: HypothesisSessionState) -> HypothesisSessionState:
        round_number = int(state.artifacts.get("ranking_round", 0)) + 1
        state.artifacts["ranking_round"] = round_number
        matches = run_pairwise_ranking(
            state.registry,
            round_number=round_number,
            ollama_config=state.config.get("_selected_llm", {}),
            knowledge_context=state.context_blocks.get("knowledge_graph", ""),
        )
        state.matches.extend(matches)
        state.artifacts["top_hypotheses"] = state.registry.top(int(state.config.get("hypothesis", {}).get("top_k", 5)), include_pending=True)
        return state
