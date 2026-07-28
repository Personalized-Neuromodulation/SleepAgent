from __future__ import annotations

import re
from dataclasses import dataclass

from .models import CrawledPaperMetadata


TERMS = (
    "sleep deprivation", "sleep restriction", "sleep quality", "sleep apnea",
    "slow wave", "functional connectivity", "resting-state", "polysomnography",
    "insomnia", "circadian", "chronotype", "hypersomnia", "narcolepsy",
    "sleep", "rem", "nrem", "eeg", "fmri",
)


@dataclass(frozen=True)
class RelevanceResult:
    score: float
    matched_terms: list[str]
    status: str


def classify_relevance(metadata: CrawledPaperMetadata) -> RelevanceResult:
    title = metadata.title.casefold()
    secondary = " ".join(
        [metadata.abstract or "", " ".join(metadata.keywords),
         " ".join(metadata.subject_headings), metadata.article_type or ""]
    ).casefold()
    matched = [term for term in TERMS if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", f"{title} {secondary}")]
    title_hits = sum(term in title for term in matched)
    score = min(1.0, title_hits * 0.55 + (len(matched) - title_hits) * 0.2)
    status = "relevant" if title_hits or score >= 0.4 else "uncertain" if matched else "not_relevant"
    return RelevanceResult(score, matched, status)
