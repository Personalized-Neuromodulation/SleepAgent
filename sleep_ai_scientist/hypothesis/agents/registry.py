from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_json, write_csv, write_json
from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.schemas.hypothesis import (
    Hypothesis,
    HypothesisLineageRecord,
    HypothesisReview,
    HypothesisStatus,
    ProximityEdge,
    TournamentMatch,
    utc_now_iso,
)


def _dump_model(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


class HypothesisRegistry:
    """Local registry for generated hypotheses and their tournament metadata."""

    def __init__(self, session_id: str = "default") -> None:
        self.session_id = session_id
        self.hypotheses: dict[str, Hypothesis] = {}
        self.reviews: list[HypothesisReview] = []
        self.matches: list[TournamentMatch] = []
        self.proximity_edges: list[ProximityEdge] = []

    def save_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        existing = self.hypotheses.get(hypothesis.hypothesis_id)
        if existing:
            hypothesis.created_at = existing.created_at
        hypothesis.updated_at = utc_now_iso()
        self.hypotheses[hypothesis.hypothesis_id] = hypothesis
        return hypothesis

    def add_hypothesis(
        self,
        *,
        title: str,
        summary: str,
        content: str,
        rationale: str,
        generation_strategy: str,
        generation_round: int = 0,
        session_id: str | None = None,
        experimental_plan: str = "",
        novelty_assessment: str = "",
        key_assumptions: list[str] | None = None,
        citations: list[str] | None = None,
        parent_ids: list[str] | None = None,
        elo_rating: float = 1200.0,
        rating_deviation: float = 350.0,
        volatility: float = 0.06,
        matches_played: int = 0,
        wins: int = 0,
        losses: int = 0,
        draws: int = 0,
        status: HypothesisStatus = HypothesisStatus.pending_review,
        metadata: dict[str, Any] | None = None,
    ) -> Hypothesis:
        sid = session_id or self.session_id
        hypothesis_id = stable_id("hypothesis", sid, title, summary, generation_strategy)
        return self.save_hypothesis(
            Hypothesis(
                hypothesis_id=hypothesis_id,
                session_id=sid,
                title=title,
                summary=summary,
                content=content,
                rationale=rationale,
                experimental_plan=experimental_plan,
                novelty_assessment=novelty_assessment,
                key_assumptions=key_assumptions or [],
                citations=citations or [],
                generation_strategy=generation_strategy,
                generation_round=generation_round,
                parent_ids=parent_ids or [],
                elo_rating=elo_rating,
                rating_deviation=rating_deviation,
                volatility=volatility,
                matches_played=matches_played,
                wins=wins,
                losses=losses,
                draws=draws,
                status=status,
                metadata=metadata or {},
            )
        )

    def add_review(self, review: HypothesisReview) -> None:
        self.reviews.append(review)

    def add_match(self, match: TournamentMatch) -> None:
        self.matches.append(match)

    def set_status(self, hypothesis_id: str, status: HypothesisStatus) -> None:
        hypothesis = self.hypotheses[hypothesis_id]
        hypothesis.status = status
        hypothesis.updated_at = utc_now_iso()

    def update_rating(
        self,
        hypothesis_id: str,
        elo_rating: float,
        rating_deviation: float | None = None,
        volatility: float | None = None,
        matches_played: int | None = None,
        wins: int | None = None,
        losses: int | None = None,
        draws: int | None = None,
    ) -> None:
        hypothesis = self.hypotheses[hypothesis_id]
        hypothesis.elo_rating = elo_rating
        if rating_deviation is not None:
            hypothesis.rating_deviation = rating_deviation
        if volatility is not None:
            hypothesis.volatility = volatility
        if matches_played is not None:
            hypothesis.matches_played = matches_played
        if wins is not None:
            hypothesis.wins = wins
        if losses is not None:
            hypothesis.losses = losses
        if draws is not None:
            hypothesis.draws = draws
        hypothesis.updated_at = utc_now_iso()

    def all(self) -> list[Hypothesis]:
        return list(self.hypotheses.values())

    def pending_review(self) -> list[Hypothesis]:
        return [h for h in self.all() if h.status == HypothesisStatus.pending_review]

    def active(self) -> list[Hypothesis]:
        return [h for h in self.all() if h.status == HypothesisStatus.active]

    def top(self, n: int = 10, include_pending: bool = False) -> list[Hypothesis]:
        allowed = {HypothesisStatus.active}
        if include_pending:
            allowed.add(HypothesisStatus.pending_review)
        rows = [h for h in self.all() if h.status in allowed]
        return sorted(rows, key=lambda h: h.elo_rating, reverse=True)[:n]

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for hypothesis in self.all():
            key = hypothesis.status.value if hasattr(hypothesis.status, "value") else str(hypothesis.status)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def lineage(self) -> list[HypothesisLineageRecord]:
        return [
            HypothesisLineageRecord(
                hypothesis_id=h.hypothesis_id,
                parent_ids=h.parent_ids,
                generation_strategy=h.generation_strategy,
                generation_round=h.generation_round,
            )
            for h in self.all()
        ]

    def write_outputs(self, output_dir: Path, top_k: int = 5) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        hypotheses = [_dump_model(item) for item in self.all()]
        write_json(output_dir / "hypothesis_pool.json", hypotheses)
        write_json(output_dir / "top_k_hypotheses.json", [_dump_model(item) for item in self.top(top_k, include_pending=True)])
        write_json(output_dir / "hypothesis_lineage.json", [_dump_model(item) for item in self.lineage()])
        write_csv(
            output_dir / "hypothesis_registry.csv",
            hypotheses,
            fieldnames=[
                "hypothesis_id",
                "session_id",
                "title",
                "summary",
                "generation_strategy",
                "generation_round",
                "elo_rating",
                "rating_deviation",
                "status",
                "parent_ids",
                "created_at",
                "updated_at",
            ],
        )

    @classmethod
    def from_json(cls, path: Path, session_id: str = "default") -> "HypothesisRegistry":
        registry = cls(session_id=session_id)
        if not path.exists() or path.stat().st_size == 0:
            return registry
        for row in read_json(path):
            registry.save_hypothesis(Hypothesis(**row))
        return registry
