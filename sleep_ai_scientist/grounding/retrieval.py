from __future__ import annotations

import math
import re
import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import resolve_path
from sleep_ai_scientist.common.io import ensure_parent
from sleep_ai_scientist.hypothesis.agents.embedding import LocalMiniLMEmbeddingClient, dense_cosine
from sleep_ai_scientist.schemas.literature import LiteratureRecord


TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]+")


@dataclass
class RetrievalResult:
    paper_id: str
    score: float
    matched_text: str
    source: str


def tokenize(text: str) -> list[str]:
    """Tokenize English/identifier-like text for deterministic local retrieval."""
    return [token.lower() for token in TOKEN_RE.findall(text)]


def rewrite_query(query: str) -> str:
    """Placeholder for future query rewrite; grounding keeps the query unchanged."""
    return query.strip()


def _document_text(record: LiteratureRecord) -> str:
    return " ".join([record.title, record.abstract, " ".join(record.keywords), record.notes])


def keyword_retrieve(query: str, records: list[LiteratureRecord], top_k: int = 10) -> list[RetrievalResult]:
    """Simple BM25-like keyword overlap retrieval without external services."""
    terms = set(tokenize(rewrite_query(query)))
    results = []
    for record in records:
        text = _document_text(record)
        doc_terms = tokenize(text)
        score = sum(1 for term in doc_terms if term in terms)
        if score:
            results.append(RetrievalResult(record.paper_id, float(score), text[:300], record.source or "literature"))
    return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]


def tfidf_retrieve(query: str, records: list[LiteratureRecord], top_k: int = 10) -> list[RetrievalResult]:
    """Small TF-IDF cosine fallback when keyword overlap produces no hits."""
    query_counts = Counter(tokenize(rewrite_query(query)))
    documents = [Counter(tokenize(_document_text(record))) for record in records]
    n_docs = max(1, len(documents))
    doc_freq: Counter[str] = Counter()
    for doc in documents:
        for token in doc:
            doc_freq[token] += 1

    def vector(counts: Counter[str]) -> dict[str, float]:
        return {
            token: count * (math.log((1 + n_docs) / (1 + doc_freq[token])) + 1)
            for token, count in counts.items()
        }

    query_vec = vector(query_counts)
    query_norm = math.sqrt(sum(value * value for value in query_vec.values())) or 1.0
    results = []
    for record, counts in zip(records, documents):
        doc_vec = vector(counts)
        doc_norm = math.sqrt(sum(value * value for value in doc_vec.values())) or 1.0
        score = sum(query_vec.get(token, 0.0) * doc_vec.get(token, 0.0) for token in query_vec) / (query_norm * doc_norm)
        if score > 0:
            results.append(RetrievalResult(record.paper_id, score, _document_text(record)[:300], record.source or "literature"))
    return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]


def embedding_retrieve(
    query: str,
    records: list[LiteratureRecord],
    top_k: int = 10,
    *,
    embedding_config: dict[str, Any] | None = None,
) -> list[RetrievalResult]:
    """Retrieve papers with local MiniLM dense embeddings."""
    config = embedding_config or {}
    provider = str(config.get("provider", "local_minilm"))
    if provider != "local_minilm":
        raise ValueError(f"Unsupported embedding provider: {provider}")
    model = str(config.get("model", "sentence-transformers/all-MiniLM-L6-v2"))
    log_file = _embedding_log_file(config)
    started = time.perf_counter()
    _embedding_log(
        "start",
        log_file=log_file,
        provider=provider,
        model=model,
        query=query,
        record_count=len(records),
        top_k=top_k,
    )
    client = LocalMiniLMEmbeddingClient(
        model,
        local_files_only=bool(config.get("local_files_only", True)),
        device=str(config.get("device", "cpu")) if config.get("device", "cpu") else None,
        cache_folder=str(config.get("cache_folder")) if config.get("cache_folder") else None,
    )
    _embedding_log("model_loaded", log_file=log_file, provider=provider, model=model, elapsed_seconds=_elapsed(started))
    query_text = rewrite_query(query)
    document_texts = [_document_text(record) for record in records]
    encode_started = time.perf_counter()
    vectors = client.embed([query_text, *document_texts])
    vector_dim = len(vectors[0]) if vectors else 0
    _embedding_log(
        "vectors_encoded",
        log_file=log_file,
        vector_count=len(vectors),
        vector_dim=vector_dim,
        elapsed_seconds=_elapsed(encode_started),
    )
    if not vectors:
        _embedding_log("retrieval_done", log_file=log_file, hits=0, elapsed_seconds=_elapsed(started), top_hits_summary=_summarize_hits([]))
        return []
    query_vector = vectors[0]
    results = []
    for record, text, vector in zip(records, document_texts, vectors[1:]):
        score = dense_cosine(query_vector, vector)
        if score > 0:
            results.append(RetrievalResult(record.paper_id, float(score), text[:300], record.source or "literature"))
    hits = sorted(results, key=lambda item: item.score, reverse=True)[:top_k]
    _embedding_log(
        "retrieval_done",
        log_file=log_file,
        hits=len(hits),
        elapsed_seconds=_elapsed(started),
        top_hits_summary=_summarize_hits(hits),
    )
    return hits


def retrieve(
    query: str,
    records: list[LiteratureRecord],
    top_k: int = 10,
    *,
    embedding_config: dict[str, Any] | None = None,
) -> list[RetrievalResult]:
    """Retrieve papers with optional local MiniLM embeddings."""
    if embedding_config and bool(embedding_config.get("enabled", False)):
        return embedding_retrieve(query, records, top_k, embedding_config=embedding_config)
    keyword = keyword_retrieve(query, records, top_k)
    return keyword if keyword else tfidf_retrieve(query, records, top_k)


def graph_rag_retrieve(*_args, **_kwargs) -> list[RetrievalResult]:
    """Reserved GraphRAG hook; intentionally not implemented in the grounding MVP."""
    return []


def _embedding_log_file(config: dict[str, Any]) -> Path:
    return resolve_path(config.get("log_file", "logs/embedding_retrieval.log"))


def _embedding_log(event: str, *, log_file: Path, **payload: Any) -> None:
    record = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        **payload,
    }
    ensure_parent(log_file)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(_embedding_message(event, payload), flush=True)


def _summarize_hits(hits: list[RetrievalResult], *, preview: int = 3) -> dict[str, Any]:
    scores = [float(hit.score) for hit in hits]
    return {
        "count": len(hits),
        "paper_ids": [hit.paper_id for hit in hits[:preview]],
        "score_min": round(min(scores), 6) if scores else None,
        "score_max": round(max(scores), 6) if scores else None,
    }


def _embedding_message(event: str, payload: dict[str, Any]) -> str:
    if event == "start":
        return f"[embedding] start provider={payload.get('provider')} model={payload.get('model')} records={payload.get('record_count')} top_k={payload.get('top_k')}"
    if event == "model_loaded":
        return f"[embedding] model loaded model={payload.get('model')} elapsed={payload.get('elapsed_seconds')}s"
    if event == "vectors_encoded":
        return f"[embedding] vectors encoded count={payload.get('vector_count')} dim={payload.get('vector_dim')} elapsed={payload.get('elapsed_seconds')}s"
    if event == "retrieval_done":
        return f"[embedding] retrieval done hits={payload.get('hits')} elapsed={payload.get('elapsed_seconds')}s"
    return f"[embedding] {event}"


def _elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)
