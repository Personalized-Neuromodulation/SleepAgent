from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from paper_rag.config import Settings
from paper_rag.db import Database
from paper_rag.embeddings import EmbeddingService


@dataclass(slots=True)
class SearchResult:
    chunk_id: UUID
    paper_id: UUID
    title: str
    doi: str | None
    journal: str
    section_title: str
    section_type: str
    page_start: int | None
    page_end: int | None
    content: str
    score: float
    vector_score: float = 0.0
    keyword_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["chunk_id"] = str(self.chunk_id)
        value["paper_id"] = str(self.paper_id)
        return value


class HybridRetriever:
    """Dense + PostgreSQL full-text retrieval, fused with reciprocal rank fusion."""

    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        self.embedder = EmbeddingService(
            settings.embedding_model,
            settings.embedding_device,
            settings.embedding_batch_size,
        )

    def search(
        self,
        query: str,
        top_k: int = 8,
        journal: str | None = None,
        year: int | None = None,
        per_paper: int = 2,
        expand_parent: bool = True,
    ) -> list[SearchResult]:
        query = query.strip()
        if not query:
            return []
        candidate_count = max(top_k * 6, 30)
        query_vector = self.embedder.encode_query(query)
        if len(query_vector) != self.settings.embedding_dimension:
            raise ValueError("查询向量维度与数据库配置不一致")

        filters, parameters = self._filters(journal, year)
        filter_sql = "".join(filters)
        with self.database.connection() as connection:
            vector_rows = connection.execute(
                f"""
                SELECT c.chunk_id, c.paper_id, c.parent_chunk_id, p.title, p.doi,
                       p.journal, c.section_title, c.section_type,
                       c.page_start, c.page_end, c.content,
                       1 - (e.embedding <=> %s) AS relevance
                FROM chunk_embeddings e
                JOIN chunks c ON c.chunk_id = e.chunk_id
                JOIN document_versions v ON v.document_version_id = c.document_version_id
                JOIN papers p ON p.paper_id = c.paper_id
                WHERE e.model_name = %s AND c.chunk_level = 'child'
                  AND v.is_active = TRUE
                  {filter_sql}
                ORDER BY e.embedding <=> %s
                LIMIT %s
                """,
                (query_vector, self.settings.embedding_model, *parameters, query_vector, candidate_count),
            ).fetchall()
            keyword_rows = connection.execute(
                f"""
                SELECT c.chunk_id, c.paper_id, c.parent_chunk_id, p.title, p.doi,
                       p.journal, c.section_title, c.section_type,
                       c.page_start, c.page_end, c.content,
                       ts_rank_cd(c.search_vector, websearch_to_tsquery('simple', %s)) AS relevance
                FROM chunks c
                JOIN document_versions v ON v.document_version_id = c.document_version_id
                JOIN papers p ON p.paper_id = c.paper_id
                WHERE c.chunk_level = 'child'
                  AND v.is_active = TRUE
                  AND c.search_vector @@ websearch_to_tsquery('simple', %s)
                  {filter_sql}
                ORDER BY relevance DESC
                LIMIT %s
                """,
                (query, query, *parameters, candidate_count),
            ).fetchall()

            fused = self._rrf(vector_rows, keyword_rows)
            selected: list[tuple[Any, float, float, float]] = []
            paper_counts: dict[UUID, int] = {}
            for row, fused_score, vector_score, keyword_score in fused:
                paper_id = row[1]
                if paper_counts.get(paper_id, 0) >= per_paper:
                    continue
                selected.append((row, fused_score, vector_score, keyword_score))
                paper_counts[paper_id] = paper_counts.get(paper_id, 0) + 1
                if len(selected) >= top_k:
                    break

            parent_ids = [row[2] for row, *_ in selected if row[2] is not None]
            parent_content: dict[UUID, str] = {}
            if expand_parent and parent_ids:
                parent_content = dict(
                    connection.execute(
                        "SELECT chunk_id, content FROM chunks WHERE chunk_id = ANY(%s)",
                        (parent_ids,),
                    ).fetchall()
                )

        return [
            SearchResult(
                chunk_id=row[0],
                paper_id=row[1],
                title=row[3],
                doi=row[4],
                journal=row[5],
                section_title=row[6],
                section_type=row[7],
                page_start=row[8],
                page_end=row[9],
                content=parent_content.get(row[2], row[10]),
                score=fused_score,
                vector_score=vector_score,
                keyword_score=keyword_score,
            )
            for row, fused_score, vector_score, keyword_score in selected
        ]

    @staticmethod
    def _filters(journal: str | None, year: int | None) -> tuple[list[str], list[Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if journal:
            clauses.append(" AND p.journal ILIKE %s")
            parameters.append(f"%{journal}%")
        if year:
            clauses.append(" AND EXTRACT(YEAR FROM p.publication_date) = %s")
            parameters.append(year)
        return clauses, parameters

    @staticmethod
    def _rrf(vector_rows: list[tuple], keyword_rows: list[tuple]) -> list[tuple[Any, float, float, float]]:
        scores: dict[UUID, float] = {}
        rows: dict[UUID, tuple] = {}
        vector_scores: dict[UUID, float] = {}
        keyword_scores: dict[UUID, float] = {}
        rrf_k = 60
        for rank, row in enumerate(vector_rows, start=1):
            chunk_id = row[0]
            rows[chunk_id] = row
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            vector_scores[chunk_id] = float(row[11])
        for rank, row in enumerate(keyword_rows, start=1):
            chunk_id = row[0]
            rows[chunk_id] = row
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            keyword_scores[chunk_id] = float(row[11])
        ordered = sorted(scores, key=scores.get, reverse=True)
        return [
            (rows[key], scores[key], vector_scores.get(key, 0.0), keyword_scores.get(key, 0.0))
            for key in ordered
        ]
