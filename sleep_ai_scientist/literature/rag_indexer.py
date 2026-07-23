from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import ensure_parent
from sleep_ai_scientist.hypothesis.agents.embedding import LocalMiniLMEmbeddingClient
from sleep_ai_scientist.storage.models import Paper, PaperSource, RagChunk, utc_now


def build_rag_index(session: Session, output_jsonl: str | Path, embedding_config: dict[str, Any] | None = None) -> dict[str, Any]:
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
    embedding_result = _embed_chunks(chunks, embedding_config or {})
    _upsert_rag_chunks(session, chunks, embedding_result)
    output_path = Path(output_jsonl)
    ensure_parent(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return {"chunk_count": len(chunks), "path": str(output_path), "embedding": embedding_result}


def _upsert_rag_chunks(session: Session, chunks: list[dict[str, Any]], embedding_result: dict[str, Any]) -> None:
    provider = embedding_result.get("provider") if embedding_result.get("enabled") else None
    model = embedding_result.get("model") if embedding_result.get("enabled") else None
    for chunk in chunks:
        vector = chunk.get("embedding")
        payload = {
            "paper_id": str(chunk["paper_id"]),
            "chunk_type": "abstract",
            "text": str(chunk.get("text", "")),
            "embedding_provider": str(provider) if provider else None,
            "embedding_model": str(model) if model else None,
            "embedding_dim": len(vector) if isinstance(vector, list) else None,
            "embedding_json": vector if isinstance(vector, list) else None,
            "metadata_json": chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {},
        }
        existing = session.get(RagChunk, str(chunk["chunk_id"]))
        if existing is None:
            session.add(RagChunk(chunk_id=str(chunk["chunk_id"]), **payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.updated_at = utc_now()
    session.flush()


def _embed_chunks(chunks: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    if not bool(config.get("enabled", False)):
        return {"enabled": False}
    provider = str(config.get("provider", "local_minilm"))
    if provider != "local_minilm":
        raise ValueError(f"Unsupported embedding provider: {provider}")
    model = str(config.get("model", "sentence-transformers/all-MiniLM-L6-v2"))
    local_files_only = bool(config.get("local_files_only", True))
    device = str(config.get("device", "cpu")) if config.get("device", "cpu") else None
    cache_folder = str(config.get("cache_folder")) if config.get("cache_folder") else None
    log_file = resolve_path(config.get("log_file", "logs/embedding_retrieval.log"))
    started = time.perf_counter()
    texts = [str(chunk.get("text", "")) for chunk in chunks]
    _log_embedding(
        "rag_index_start",
        log_file=log_file,
        provider=provider,
        model=model,
        chunk_count=len(chunks),
        local_files_only=local_files_only,
        device=device or "",
    )
    client = LocalMiniLMEmbeddingClient(model, local_files_only=local_files_only, device=device, cache_folder=cache_folder)
    vectors = client.embed(texts) if texts else []
    vector_dim = len(vectors[0]) if vectors else 0
    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = [float(value) for value in vector]
        chunk.setdefault("metadata", {})["embedding_model"] = model
        chunk.setdefault("metadata", {})["embedding_provider"] = provider
    _log_embedding("rag_vectors_encoded", log_file=log_file, vector_count=len(vectors), vector_dim=vector_dim, elapsed_seconds=_elapsed(started))
    _log_embedding("rag_index_done", log_file=log_file, chunk_count=len(chunks), vector_count=len(vectors), vector_dim=vector_dim, elapsed_seconds=_elapsed(started))
    return {
        "enabled": True,
        "provider": provider,
        "model": model,
        "local_files_only": local_files_only,
        "device": device,
        "vector_count": len(vectors),
        "vector_dim": vector_dim,
        "log_file": str(log_file),
    }


def _log_embedding(event: str, *, log_file: Path, **payload: Any) -> None:
    ensure_parent(log_file)
    record = {"event": event, "timestamp": datetime.now(UTC).isoformat(), **payload}
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(_message(event, payload), flush=True)


def _message(event: str, payload: dict[str, Any]) -> str:
    if event == "rag_index_start":
        return f"[embedding] rag index start provider={payload.get('provider')} model={payload.get('model')} chunks={payload.get('chunk_count')}"
    if event == "rag_vectors_encoded":
        return f"[embedding] rag vectors encoded count={payload.get('vector_count')} dim={payload.get('vector_dim')} elapsed={payload.get('elapsed_seconds')}s"
    if event == "rag_index_done":
        return f"[embedding] rag index done chunks={payload.get('chunk_count')} vectors={payload.get('vector_count')} elapsed={payload.get('elapsed_seconds')}s"
    return f"[embedding] {event}"


def _elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)
