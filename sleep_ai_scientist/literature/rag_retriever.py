from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import ensure_parent
from sleep_ai_scientist.hypothesis.agents.embedding import LocalMiniLMEmbeddingClient, dense_cosine
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.models import Paper, RagChunk


def retrieve_literature_records_from_db(
    session: Session,
    query: str,
    *,
    top_k: int = 20,
    embedding_config: dict[str, Any] | None = None,
) -> tuple[list[LiteratureRecord], dict[str, Any]]:
    """Retrieve top-K literature records from persisted RAG chunk embeddings."""
    config = embedding_config or {}
    if not bool(config.get("enabled", False)):
        return _retrieve_by_keyword(session, query, top_k=top_k, config=config)
    provider = str(config.get("provider", "local_minilm"))
    if provider != "local_minilm":
        raise ValueError(f"Unsupported embedding provider: {provider}")
    model = str(config.get("model", "sentence-transformers/all-MiniLM-L6-v2"))
    log_file = resolve_path(config.get("log_file", "logs/embedding_retrieval.log"))
    started = time.perf_counter()
    chunks = list(
        session.scalars(
            select(RagChunk)
            .where(RagChunk.embedding_json.is_not(None))
            .where(RagChunk.embedding_model == model)
            .order_by(RagChunk.chunk_id)
        )
    )
    if not chunks:
        chunks = list(session.scalars(select(RagChunk).where(RagChunk.embedding_json.is_not(None)).order_by(RagChunk.chunk_id)))
    _log(
        "db_rag_retrieval_start",
        log_file=log_file,
        provider=provider,
        model=model,
        query=query,
        top_k=top_k,
        available_chunks=len(chunks),
    )
    if not chunks:
        _log("db_rag_retrieval_done", log_file=log_file, hits=0, elapsed_seconds=_elapsed(started))
        return [], {"source": "literature_db_rag", "enabled": True, "retrieval_hits": 0, "available_chunks": 0}
    client = LocalMiniLMEmbeddingClient(
        model,
        local_files_only=bool(embedding_config.get("local_files_only", True)),
        device=str(embedding_config.get("device", "cpu")) if embedding_config.get("device", "cpu") else None,
        cache_folder=str(embedding_config.get("cache_folder")) if embedding_config.get("cache_folder") else None,
    )
    query_vector = client.embed([query])[0]
    scored = []
    for chunk in chunks:
        vector = chunk.embedding_json or []
        score = dense_cosine(query_vector, [float(value) for value in vector])
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected_chunks = scored[:top_k]
    records: list[LiteratureRecord] = []
    seen_papers: set[str] = set()
    top_hits: list[dict[str, Any]] = []
    for score, chunk in selected_chunks:
        if chunk.paper_id in seen_papers:
            continue
        paper = session.get(Paper, chunk.paper_id)
        if paper is None:
            continue
        seen_papers.add(chunk.paper_id)
        records.append(_paper_to_record(paper))
        top_hits.append({"paper_id": paper.paper_id, "chunk_id": chunk.chunk_id, "score": round(float(score), 6)})
    _log(
        "db_rag_retrieval_done",
        log_file=log_file,
        hits=len(records),
        available_chunks=len(chunks),
        elapsed_seconds=_elapsed(started),
        top_hits_summary=_summarize_hits(top_hits),
    )
    return records, {
        "source": "literature_db_rag",
        "enabled": True,
        "retrieval_hits": len(records),
        "available_chunks": len(chunks),
        "top_k": top_k,
        "embedding_provider": provider,
        "embedding_model": model,
        "top_hits_summary": _summarize_hits(top_hits),
    }


def _retrieve_by_keyword(session: Session, query: str, *, top_k: int, config: dict[str, Any]) -> tuple[list[LiteratureRecord], dict[str, Any]]:
    log_file = resolve_path(config.get("log_file", "logs/embedding_retrieval.log"))
    started = time.perf_counter()
    chunks = list(session.scalars(select(RagChunk).order_by(RagChunk.chunk_id)))
    _log("db_keyword_retrieval_start", log_file=log_file, query=query, top_k=top_k, available_chunks=len(chunks))
    query_terms = _terms(query)
    scored = []
    for chunk in chunks:
        metadata = chunk.metadata_json or {}
        haystack = " ".join(
            [
                chunk.text or "",
                str(metadata.get("title", "")),
                " ".join(str(item) for item in metadata.get("query_groups", []) if item),
            ]
        )
        terms = _terms(haystack)
        overlap = query_terms & terms
        if overlap:
            scored.append((len(overlap), chunk))
    scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
    records: list[LiteratureRecord] = []
    seen_papers: set[str] = set()
    top_hits: list[dict[str, Any]] = []
    for score, chunk in scored:
        if chunk.paper_id in seen_papers:
            continue
        paper = session.get(Paper, chunk.paper_id)
        if paper is None:
            continue
        seen_papers.add(chunk.paper_id)
        records.append(_paper_to_record(paper))
        top_hits.append({"paper_id": paper.paper_id, "chunk_id": chunk.chunk_id, "score": int(score)})
        if len(records) >= top_k:
            break
    _log(
        "db_keyword_retrieval_done",
        log_file=log_file,
        hits=len(records),
        available_chunks=len(chunks),
        elapsed_seconds=_elapsed(started),
        top_hits_summary=_summarize_hits(top_hits),
    )
    return records, {
        "source": "literature_db_rag",
        "enabled": True,
        "retrieval_mode": "keyword",
        "retrieval_hits": len(records),
        "available_chunks": len(chunks),
        "top_k": top_k,
        "top_hits_summary": _summarize_hits(top_hits),
    }


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", text.lower()) if len(term) > 2}


def _paper_to_record(paper: Paper) -> LiteratureRecord:
    return LiteratureRecord(
        paper_id=paper.paper_id,
        title=paper.title,
        abstract=paper.abstract or "",
        year=paper.year,
        doi=paper.doi or "",
        pmid=paper.pmid or "",
        pmcid=paper.pmcid,
        source=";".join(paper.source_providers_json or []) or (paper.source or ""),
        keywords=paper.keywords_json or [],
        url=paper.url or "",
        journal=paper.journal,
        publication_type=paper.publication_type,
        authors=paper.authors_json or [],
        citation_count=paper.citation_count,
        citation_source=paper.citation_source,
        citation_count_age_normalized=paper.citation_count_age_normalized,
        is_open_access=paper.is_open_access,
        provider=";".join(paper.source_providers_json or []),
        semantic_scholar_id=paper.semantic_scholar_id,
        openalex_id=paper.openalex_id,
        crossref_id=paper.crossref_id,
        first_author=paper.first_author,
        retrieval_channel=";".join(paper.retrieval_channels_json or []),
        journal_priority_score=paper.journal_priority_score,
    )


def _log(event: str, *, log_file: Path, **payload: Any) -> None:
    ensure_parent(log_file)
    record = {"event": event, "timestamp": datetime.now(UTC).isoformat(), **payload}
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(_message(event, payload), flush=True)


def _summarize_hits(hits: list[dict[str, Any]], *, preview: int = 3) -> dict[str, Any]:
    scores = [float(item["score"]) for item in hits if item.get("score") is not None]
    return {
        "count": len(hits),
        "paper_ids": [str(item.get("paper_id", "")) for item in hits[:preview]],
        "score_min": round(min(scores), 6) if scores else None,
        "score_max": round(max(scores), 6) if scores else None,
    }


def _message(event: str, payload: dict[str, Any]) -> str:
    if event == "db_rag_retrieval_start":
        return f"[embedding] db rag retrieval start model={payload.get('model')} chunks={payload.get('available_chunks')} top_k={payload.get('top_k')}"
    if event == "db_rag_retrieval_done":
        return f"[embedding] db rag retrieval done hits={payload.get('hits')} elapsed={payload.get('elapsed_seconds')}s"
    if event == "db_keyword_retrieval_start":
        return f"[retrieval] db keyword retrieval start chunks={payload.get('available_chunks')} top_k={payload.get('top_k')}"
    if event == "db_keyword_retrieval_done":
        return f"[retrieval] db keyword retrieval done hits={payload.get('hits')} elapsed={payload.get('elapsed_seconds')}s"
    return f"[embedding] {event}"


def _elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)
