from __future__ import annotations

import json
from collections import Counter
from typing import Any

from sleep_ai_scientist.common.utils import normalize_text
from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.hypothesis.agents.llm import LLMError, build_llm_client, llm_enabled, load_prompt, normalize_llm_config
from sleep_ai_scientist.hypothesis.agents.state import HypothesisSessionState
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord
from sleep_ai_scientist.schemas.hypothesis import GenerationStrategy, Hypothesis


def _top_terms(evidence: list[EvidenceRecord], field: str, n: int = 5) -> list[str]:
    counts = Counter(normalize_text(getattr(item, field, "")) for item in evidence)
    return [term for term, _ in counts.most_common(n) if term]


def _select_evidence(evidence: list[EvidenceRecord], strategy: str, limit: int = 4) -> list[EvidenceRecord]:
    if strategy == GenerationStrategy.literature_exploration.value:
        ordered = sorted(evidence, key=lambda item: item.evidence_quality_score or item.confidence_score, reverse=True)
    elif strategy == GenerationStrategy.assumption_chaining.value:
        ordered = sorted(evidence, key=lambda item: (item.mechanism, item.variable_or_feature))
    elif strategy == GenerationStrategy.research_expansion.value:
        ordered = sorted(evidence, key=lambda item: item.modality)
    else:
        ordered = sorted(evidence, key=lambda item: item.paper_id)
    return ordered[:limit]


def _evidence_context(evidence: list[EvidenceRecord]) -> str:
    lines = []
    for index, item in enumerate(evidence, start=1):
        lines.append(
            "\n".join(
                [
                    f"[E{index}] paper_id={item.paper_id}",
                    f"claim={item.claim}",
                    f"population={item.population}",
                    f"modality={item.modality}",
                    f"variable={item.variable_or_feature}",
                    f"mechanism={item.mechanism}",
                    f"direction={item.direction.value if hasattr(item.direction, 'value') else item.direction}",
                    f"quality={item.evidence_quality_score if item.evidence_quality_score is not None else item.confidence_score}",
                ]
            )
        )
    return "\n\n".join(lines)


def _existing_context(registry: HypothesisRegistry | None) -> str:
    if registry is None:
        return ""
    rows = registry.top(8, include_pending=True)
    return "\n".join(f"- {item.title}: {item.summary}" for item in rows)


def _context_with_rlef(base: str, rlef_context: str = "", prior_context: str = "") -> str:
    parts = [base]
    if prior_context:
        parts.append(prior_context)
    if rlef_context:
        parts.append(rlef_context)
    return "\n\n".join(part for part in parts if part)


DOMAIN_METADATA_FIELDS = [
    "sleep_phenotype",
    "neural_mechanism",
    "brain_regions",
    "brain_networks",
    "modalities",
    "measurable_variables",
    "directional_prediction",
    "falsification_criteria",
    "supporting_evidence",
    "contradictory_evidence",
    "knowledge_graph_paths",
]


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return [str(value).strip()] if str(value).strip() else []


def _payload_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return ""


def _flatten_hypothesis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ["hypothesis", "candidate_hypothesis", "candidate", "result"]:
        nested = payload.get(key)
        if isinstance(nested, dict):
            merged = dict(nested)
            for outer_key, value in payload.items():
                if outer_key not in merged and outer_key != key:
                    merged[outer_key] = value
            return merged
    return payload


def _coerce_hypothesis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = _flatten_hypothesis_payload(payload)
    coerced = dict(payload)
    aliases = {
        "title": ("title", "hypothesis_title", "name"),
        "summary": ("summary", "abstract", "brief_summary"),
        "content": ("content", "hypothesis", "hypothesis_statement", "statement", "full_hypothesis", "description"),
        "rationale": ("rationale", "scientific_rationale", "reasoning", "justification"),
        "experimental_plan": ("experimental_plan", "experimentalPlan", "test_plan", "experiment_plan", "analysis_plan"),
        "novelty_assessment": ("novelty_assessment", "noveltyAssessment", "novelty"),
        "key_assumptions": ("key_assumptions", "keyAssumptions", "assumptions"),
    }
    for target, keys in aliases.items():
        value = _payload_value(payload, *keys)
        if value not in (None, ""):
            coerced[target] = value
    return coerced


def _missing_required_fields(payload: dict[str, Any]) -> list[str]:
    return [
        field
        for field in ["title", "summary", "content", "rationale"]
        if not normalize_text(payload.get(field, ""))
    ]


def _repair_hypothesis_schema(
    client: Any,
    payload: dict[str, Any],
    *,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    return client.call_json(
        [
            {
                "role": "system",
                "content": "You are a strict JSON schema repair agent. Return only valid JSON.",
            },
            {
                "role": "user",
                "content": (
                    "Rewrite the following hypothesis JSON into exactly this schema while preserving the scientific meaning. "
                    "If a field is implicit, infer it from the available content.\n\n"
                    "Required schema:\n"
                    '{\n'
                    '  "title": "Concise title",\n'
                    '  "summary": "1-3 sentence summary",\n'
                    '  "content": "Full hypothesis statement",\n'
                    '  "rationale": "Scientific rationale grounded in evidence",\n'
                    '  "experimental_plan": "Concrete analysis or experiment plan",\n'
                    '  "novelty_assessment": "Why this is novel",\n'
                    '  "key_assumptions": ["assumption 1"],\n'
                    '  "citations": ["paper_id or evidence id"]\n'
                    '}\n\n'
                    "Original JSON:\n"
                    f"{json.dumps(payload, ensure_ascii=False)[:6000]}"
                ),
            },
        ],
        max_tokens=max_tokens,
        temperature=min(temperature, 0.1),
    )


def _generate_with_llm(
    selected: list[EvidenceRecord],
    *,
    session_id: str,
    strategy: str,
    round_number: int,
    registry: HypothesisRegistry,
    llm_config: dict[str, Any],
    rlef_context: str = "",
    prior_context: str = "",
    knowledge_context: str = "",
) -> Hypothesis | None:
    llm_config = normalize_llm_config(llm_config)
    client = build_llm_client(llm_config)
    temperature = float(llm_config.get("temperature", 0.2))
    system, prompt, max_tokens = load_prompt(
        "generation",
        strategy,
        {
            "evidence_context": _evidence_context(selected),
            "existing_hypotheses": _context_with_rlef(_existing_context(registry) or "None yet.", rlef_context, prior_context),
            "knowledge_context": knowledge_context or "No knowledge graph context was provided.",
        },
    )
    if strategy == GenerationStrategy.scientific_debate.value:
        turn1 = client.call(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt + "\n\nScientist A: propose a bold candidate hypothesis with rationale."}],
            max_tokens=max_tokens,
            temperature=temperature,
        ).content
        payload = client.call_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt + "\n\nScientist A: propose a bold candidate hypothesis with rationale."},
                {"role": "assistant", "content": turn1},
                {
                    "role": "user",
                    "content": (
                        "Scientist B: critique weaknesses, missing evidence, and alternative interpretations. "
                        "Then Scientist A: refine the hypothesis in response. "
                        "Finally output only the JSON object."
                    ),
                },
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
    else:
        payload = client.call_json(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
    payload = _coerce_hypothesis_payload(payload)
    missing = _missing_required_fields(payload)
    if missing:
        payload = _coerce_hypothesis_payload(
            _repair_hypothesis_schema(client, payload, max_tokens=max_tokens, temperature=temperature)
        )
        missing = _missing_required_fields(payload)
    title = normalize_text(payload.get("title", ""))
    summary = normalize_text(payload.get("summary", ""))
    content = normalize_text(payload.get("content", ""))
    rationale = normalize_text(payload.get("rationale", ""))
    if missing:
        preview = json.dumps(payload, ensure_ascii=False)[:1000]
        raise LLMError(f"LLM hypothesis JSON is missing required fields: {missing}. Payload preview: {preview}")
    metadata = {
        "evidence_ids": [item.evidence_id for item in selected],
        "llm_provider": client.provider,
        "llm_model": client.model,
        "llm_strategy_detail": "multi_turn_debate" if strategy == GenerationStrategy.scientific_debate.value else "single_turn_json",
    }
    for field in DOMAIN_METADATA_FIELDS:
        if field in payload:
            metadata[field] = payload[field]
    return registry.add_hypothesis(
        session_id=session_id,
        title=title,
        summary=summary,
        content=content,
        rationale=rationale,
        experimental_plan=normalize_text(payload.get("experimental_plan") or payload.get("experimentalPlan")),
        novelty_assessment=normalize_text(payload.get("novelty_assessment") or payload.get("noveltyAssessment")),
        key_assumptions=_coerce_list(payload.get("key_assumptions") or payload.get("keyAssumptions")),
        citations=_coerce_list(payload.get("citations")),
        generation_strategy=strategy,
        generation_round=round_number,
        metadata=metadata,
    )


def generate_hypothesis_from_evidence(
    evidence: list[EvidenceRecord],
    *,
    session_id: str,
    strategy: str,
    round_number: int = 0,
    registry: HypothesisRegistry | None = None,
    ollama_config: dict[str, Any] | None = None,
    rlef_context: str = "",
    prior_context: str = "",
    knowledge_context: str = "",
) -> Hypothesis | None:
    """Generate an evidence-grounded sleep-science hypothesis.

    When ``ollama_config.enabled`` is true this calls the selected provider
    directly. Failures propagate unless the caller explicitly disables LLM use.
    """
    selected = _select_evidence(evidence, strategy)
    if not selected:
        return None
    target = registry or HypothesisRegistry(session_id=session_id)

    if llm_enabled(ollama_config):
        try:
            return _generate_with_llm(
                selected,
                session_id=session_id,
                strategy=strategy,
                round_number=round_number,
                registry=target,
                llm_config=ollama_config or {},
                rlef_context=rlef_context,
                prior_context=prior_context,
                knowledge_context=knowledge_context,
            )
        except LLMError:
            if not bool(normalize_llm_config(ollama_config).get("fallback_to_rules", False)):
                raise

    mechanisms = _top_terms(selected, "mechanism", 3)
    variables = _top_terms(selected, "variable_or_feature", 3)
    modalities = _top_terms(selected, "modality", 3)
    support_count = sum(1 for item in selected if item.direction == EvidenceDirection.support)
    uncertain_count = len(selected) - support_count

    primary_mechanism = mechanisms[0]
    primary_variable = variables[0]
    modality = modalities[0] if modalities else "multimodal"

    if strategy == GenerationStrategy.scientific_debate.value:
        title = f"Debated {primary_mechanism} hypothesis for {primary_variable}"
        angle = "contrasting supportive and uncertain evidence before converging on a testable mechanism"
    elif strategy == GenerationStrategy.assumption_chaining.value:
        title = f"{primary_mechanism.title()} chain predicts {primary_variable}"
        angle = "linking an upstream sleep mechanism to intermediate measurable assumptions"
    elif strategy == GenerationStrategy.research_expansion.value:
        title = f"Unexplored {modality} marker of {primary_mechanism}"
        angle = "expanding toward a modality or variable cluster not yet overrepresented"
    else:
        title = f"{primary_mechanism.title()} explains {primary_variable} alteration"
        angle = "synthesizing the strongest available evidence into one mechanistic proposal"

    summary = (
        f"{primary_mechanism} may drive measurable change in {primary_variable} "
        f"among sleep-disorder populations, detectable with {modality} features."
    )
    content = (
        f"This hypothesis proposes that {primary_mechanism} is not merely correlated with sleep disturbance "
        f"but acts as an organizing mechanism that changes {primary_variable}. The proposal is grounded in "
        f"{len(selected)} evidence records spanning {', '.join(modalities) or 'available modalities'}. "
        f"It should be tested by modeling {primary_variable} against mechanism-linked features while controlling "
        f"for known sleep severity and data-quality covariates."
    )
    rationale = (
        f"The selected evidence contains {support_count} supportive and {uncertain_count} uncertain/refuting records. "
        f"The generation strategy used {angle}. This keeps the hypothesis anchored to observed variables rather than "
        f"inventing unavailable measurements."
    )
    experimental_plan = (
        f"Use the analysis-ready profile to identify approved features for {', '.join(variables)}. Fit a prespecified "
        f"model with negative controls, then test whether {primary_mechanism} improves prediction or mediation of "
        f"sleep outcomes beyond baseline covariates."
    )
    novelty_assessment = (
        f"The novelty comes from connecting {primary_mechanism} to {primary_variable} through an explicit, "
        f"testable multimodal bridge rather than treating them as isolated findings."
    )
    key_assumptions = [
        f"{primary_mechanism} is measurable through available sleep-science features",
        f"{primary_variable} captures a downstream expression of the mechanism",
        "The association remains after quality-control and confound checks",
    ]
    citations = sorted({item.paper_id for item in selected})

    metadata = {
        "evidence_ids": [item.evidence_id for item in selected],
        "neural_mechanism": primary_mechanism,
        "modalities": modalities,
        "measurable_variables": variables,
        "directional_prediction": f"{primary_mechanism} changes {primary_variable}",
    }
    return target.add_hypothesis(
        session_id=session_id,
        title=title,
        summary=summary,
        content=content,
        rationale=rationale,
        experimental_plan=experimental_plan,
        novelty_assessment=novelty_assessment,
        key_assumptions=key_assumptions,
        citations=citations,
        generation_strategy=strategy,
        generation_round=round_number,
        metadata=metadata,
    )


def generate_initial_hypotheses(
    evidence: list[EvidenceRecord],
    *,
    session_id: str = "default",
    max_hypotheses: int = 4,
    ollama_config: dict[str, Any] | None = None,
    rlef_context: str = "",
    prior_context: str = "",
    knowledge_context: str = "",
) -> HypothesisRegistry:
    registry = HypothesisRegistry(session_id=session_id)
    strategies = [
        GenerationStrategy.literature_exploration.value,
        GenerationStrategy.scientific_debate.value,
        GenerationStrategy.assumption_chaining.value,
        GenerationStrategy.research_expansion.value,
    ]
    for round_number, strategy in enumerate(strategies[:max_hypotheses], start=1):
        generate_hypothesis_from_evidence(
            evidence,
            session_id=session_id,
            strategy=strategy,
            round_number=round_number,
            registry=registry,
            ollama_config=ollama_config,
            rlef_context=rlef_context,
            prior_context=prior_context,
            knowledge_context=knowledge_context,
        )
    return registry


class GenerationAgent:
    name = "GenerationAgent"

    def run(self, state: HypothesisSessionState) -> HypothesisSessionState:
        hypothesis_cfg = state.config.get("hypothesis", {})
        context_block = _join_context_blocks(state)
        state.registry = generate_initial_hypotheses(
            state.evidence_table,
            session_id=str(hypothesis_cfg.get("session_id", state.registry.session_id)),
            max_hypotheses=int(hypothesis_cfg.get("max_hypotheses", 4)),
            ollama_config=state.config.get("_selected_llm", {}),
            rlef_context=state.context_blocks.get("rlef_context", ""),
            prior_context=state.context_blocks.get("prior_context", ""),
            knowledge_context=context_block,
        )
        return state


def _join_context_blocks(state: HypothesisSessionState) -> str:
    blocks = [
        "## RESEARCH QUESTION\n" + state.context_blocks.get("research_question", ""),
        "## EVIDENCE SUMMARY\n" + state.context_blocks.get("evidence", ""),
        "## KNOWLEDGE GRAPH CONTEXT\n" + state.context_blocks.get("knowledge_graph", ""),
        "## PRIOR HYPOTHESES\n" + state.context_blocks.get("prior_hypotheses", ""),
    ]
    return "\n\n".join(block for block in blocks if block.strip())
