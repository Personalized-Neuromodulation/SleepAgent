from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

import typer

from paper_rag.config import settings
from paper_rag.db import Database
from paper_rag.ingestion import IngestionPipeline
from paper_rag.rag import RagService
from paper_rag.retrieval import HybridRetriever


app = typer.Typer(no_args_is_help=True, help="论文解析、入库、检索与RAG命令行")


def _database(open_pool: bool = True) -> Database:
    database = Database(settings.database_url)
    if open_pool:
        database.open()
    return database


@app.command("init-db")
def init_db(schema: Path = typer.Option(Path("db/init.sql"), exists=True, dir_okay=False)) -> None:
    """创建pgvector扩展、数据表和索引。"""
    database = _database(open_pool=False)
    database.initialize(schema)
    typer.echo("数据库初始化完成")


@app.command()
def ingest(
    csv_path: Path | None = typer.Option(None, "--csv", dir_okay=False),
    limit: int | None = typer.Option(None, min=1, help="覆盖config.yaml中的试运行行数"),
    full: bool = typer.Option(False, "--full", help="忽略limit，执行全量导入"),
    force: bool | None = typer.Option(None, help="覆盖config.yaml中的强制重建设置"),
) -> None:
    """导入download_results.csv中status=success且文件存在的论文。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    actual_csv = csv_path or settings.source_csv
    if not actual_csv.is_file():
        raise typer.BadParameter(f"CSV不存在: {actual_csv}", param_hint="--csv")
    actual_limit = None if full else (limit if limit is not None else settings.ingest_limit)
    actual_force = force if force is not None else settings.ingest_force
    database = _database()
    try:
        stats = IngestionPipeline(settings, database).ingest_csv(
            actual_csv, actual_limit, actual_force
        )
        typer.echo(json.dumps(asdict(stats), ensure_ascii=False, indent=2))
    finally:
        database.close()


@app.command()
def search(
    query: str,
    top_k: int = typer.Option(8, min=1, max=50),
    journal: str | None = None,
    year: int | None = None,
) -> None:
    """执行向量+关键词混合检索。"""
    database = _database()
    try:
        results = HybridRetriever(settings, database).search(query, top_k, journal, year)
        typer.echo(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2))
    finally:
        database.close()


@app.command()
def ask(question: str, top_k: int = typer.Option(8, min=1, max=30)) -> None:
    """检索论文证据并调用OpenAI兼容的LLM生成带引用回答。"""
    database = _database()
    try:
        retriever = HybridRetriever(settings, database)
        result = RagService(settings, retriever).answer(question, top_k)
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        database.close()


@app.command()
def status() -> None:
    """显示语料库状态。"""
    database = _database()
    try:
        with database.connection() as connection:
            document_rows = connection.execute(
                "SELECT parse_status, count(*) FROM documents GROUP BY parse_status ORDER BY parse_status"
            ).fetchall()
            counts = connection.execute(
                """
                SELECT (SELECT count(*) FROM papers),
                       (SELECT count(*) FROM sections),
                       (SELECT count(*) FROM chunks WHERE chunk_level='child'),
                       (SELECT count(*) FROM chunk_embeddings)
                """
            ).fetchone()
        typer.echo(json.dumps({
            "papers": counts[0], "sections": counts[1], "child_chunks": counts[2],
            "chunk_embeddings": counts[3], "documents": dict(document_rows),
        }, ensure_ascii=False, indent=2))
    finally:
        database.close()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
