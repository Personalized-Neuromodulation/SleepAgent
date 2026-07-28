from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Paper, PaperIdentifier
from .normalization import normalize_author, normalize_journal, normalize_title

IDENTIFIER_PRIORITY = ("doi", "pmid", "pmcid", "semantic_scholar_id", "openalex_id", "publisher_id")


@dataclass
class MatchResult:
    decision: str; paper: Paper | None; method: str; score: float | None = None; reasons: list[str] | None = None


class IdentifierConflictError(RuntimeError):
    def __init__(self, matches): super().__init__("identifier_conflict: identifiers resolve to different canonical papers"); self.matches = matches


class GlobalDeduplicator:
    def __init__(self, auto_threshold: float = 0.94, manual_threshold: float = 0.82): self.auto_threshold=auto_threshold; self.manual_threshold=manual_threshold

    def match(self, session: Session, identifiers: dict[str, str], metadata: dict) -> MatchResult:
        matches = {}
        for kind in IDENTIFIER_PRIORITY:
            if identifiers.get(kind):
                found=session.scalar(select(PaperIdentifier).where(PaperIdentifier.identifier_type==kind, PaperIdentifier.normalized_value==identifiers[kind]))
                if found: matches[kind]=session.get(Paper, found.paper_id)
        ids={p.paper_id for p in matches.values()}
        if len(ids)>1: raise IdentifierConflictError({k:v.paper_id for k,v in matches.items()})
        if matches:
            kind=next(k for k in IDENTIFIER_PRIORITY if k in matches); return MatchResult("exact_match", matches[kind], kind, 1.0, [f"exact {kind}"])
        title=normalize_title(metadata.get("title")); year=metadata.get("publication_year"); first=normalize_author((metadata.get("authors") or [""])[0]); journal=normalize_journal(metadata.get("journal"))
        if not title: return MatchResult("create_new",None,"none",0,[])
        candidates=list(session.scalars(select(Paper).where(Paper.publication_year==year))) if year else list(session.scalars(select(Paper)))
        best=None; best_score=0.0
        for paper in candidates:
            score=SequenceMatcher(None,title,paper.normalized_title).ratio()
            if score>best_score: best,best_score=paper,score
        if best:
            author_match = bool(first and any(normalize_author(v)==first for v in self._paper_authors(session,best)))
            journal_match = bool(
                journal and normalize_journal(best.journal_name) == journal
            )
            corroborated = (year is not None and best.publication_year==year) and (author_match or journal_match)
            if best_score>=self.auto_threshold and corroborated: return MatchResult("fuzzy_match",best,"title_bibliographic",best_score,["high title similarity","bibliographic corroboration"])
            if best_score>=self.manual_threshold: return MatchResult("manual_review",best,"title_similarity",best_score,["insufficient bibliographic corroboration"])
        return MatchResult("create_new",None,"none",best_score,[])

    @staticmethod
    def _paper_authors(session, paper):
        from .models import PaperAuthor

        rows = session.scalars(
            select(PaperAuthor)
            .where(PaperAuthor.paper_id == paper.paper_id)
            .order_by(PaperAuthor.author_order)
        ).all()
        return [
            row.collective_name
            or " ".join(part for part in (row.given_name, row.family_name) if part)
            for row in rows[:1]
        ]
