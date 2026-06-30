from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

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
    """Placeholder for future query rewrite; Phase 1 keeps the query unchanged."""
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


def retrieve(query: str, records: list[LiteratureRecord], top_k: int = 10) -> list[RetrievalResult]:
    """Retrieve papers using keyword overlap first, then TF-IDF fallback."""
    keyword = keyword_retrieve(query, records, top_k)
    return keyword if keyword else tfidf_retrieve(query, records, top_k)


def graph_rag_retrieve(*_args, **_kwargs) -> list[RetrievalResult]:
    """Reserved GraphRAG hook; intentionally not implemented in Phase 1."""
    return []
