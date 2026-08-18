from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from paper_rag.config import settings
from paper_rag.db import Database
from paper_rag.rag import RagService
from paper_rag.retrieval import HybridRetriever


database = Database(settings.database_url)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.open()
    yield
    database.close()


app = FastAPI(title="Paper RAG PostgreSQL", version="0.2.0", lifespan=lifespan)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)
    journal: str | None = None
    year: int | None = Field(default=None, ge=1600, le=2200)
    per_paper: int = Field(default=2, ge=1, le=10)
    expand_parent: bool = True


class RagRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=30)


@app.get("/health")
def health() -> dict[str, Any]:
    with database.connection() as connection:
        row = connection.execute(
            "SELECT count(*) FROM documents WHERE parse_status = 'embedded'"
        ).fetchone()
    return {"status": "ok", "embedded_documents": row[0]}


@app.post("/search")
def search(request: SearchRequest) -> dict[str, Any]:
    retriever = HybridRetriever(settings, database)
    results = retriever.search(
        request.query,
        request.top_k,
        request.journal,
        request.year,
        request.per_paper,
        request.expand_parent,
    )
    return {"query": request.query, "results": [item.to_dict() for item in results]}


@app.post("/rag")
def rag(request: RagRequest) -> dict[str, Any]:
    retriever = HybridRetriever(settings, database)
    return RagService(settings, retriever).answer(request.question, request.top_k)
