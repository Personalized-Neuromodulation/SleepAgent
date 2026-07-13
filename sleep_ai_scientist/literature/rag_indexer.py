from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sleep_ai_scientist.common.io import ensure_parent
from sleep_ai_scientist.storage.models import Paper, PaperSource


def build_rag_index(session: Session, output_jsonl: str | Path) -> dict[str, Any]:
    """Build one abstract chunk per canonical paper."""
    chunks: list[dict[str, Any]] = []
    for paper in session.scalars(select(Paper).order_by(Paper.paper_id)):
        if not paper.abstract:
            continue
        sources = list(session.scalars(select(PaperSource).where(PaperSource.paper_id == paper.paper_id)))
        query_groups = sorted({source.query_group for source in sources if source.query_group})
        chunk = {
            "chunk_id": f"abstract:{paper.paper_id}",
            "paper_id": paper.paper_id,
            "text": paper.abstract,
            "metadata": {
                "title": paper.title,
                "doi": paper.doi,
                "pmid": paper.pmid,
                "pmcid": paper.pmcid,
                "year": paper.year,
                "journal": paper.journal,
                "source_providers": paper.source_providers_json or [],
                "retrieval_channels": paper.retrieval_channels_json or [],
                "journal_priority_score": paper.journal_priority_score,
                "query_groups": query_groups,
            },
        }
        chunks.append(chunk)
    output_path = Path(output_jsonl)
    ensure_parent(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return {"chunk_count": len(chunks), "path": str(output_path)}
