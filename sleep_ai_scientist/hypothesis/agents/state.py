from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.hypothesis.agents.memory import ExperimentalFeedback, RewardMemoryRecord
from sleep_ai_scientist.schemas.evidence import EvidenceRecord
from sleep_ai_scientist.schemas.hypothesis import Hypothesis, HypothesisReview, TournamentMatch


@dataclass
class HypothesisSessionState:
    config: dict[str, Any]
    research_question: str
    evidence_table: list[EvidenceRecord]
    knowledge_graph: dict[str, Any] = field(default_factory=dict)
    prior_hypotheses: list[Hypothesis] = field(default_factory=list)
    experimental_feedback: list[ExperimentalFeedback] = field(default_factory=list)
    reward_memory: list[RewardMemoryRecord] = field(default_factory=list)
    registry: HypothesisRegistry = field(default_factory=HypothesisRegistry)
    reviews: list[HypothesisReview] = field(default_factory=list)
    matches: list[TournamentMatch] = field(default_factory=list)
    rejected_duplicates: list[str] = field(default_factory=list)
    context_blocks: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    output_dir: Path | None = None
    report_path: Path | None = None


class HypothesisAgent(Protocol):
    name: str

    def run(self, state: HypothesisSessionState) -> HypothesisSessionState:
        ...
