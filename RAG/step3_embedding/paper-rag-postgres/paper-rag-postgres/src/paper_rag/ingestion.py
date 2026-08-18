from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from paper_rag.chunking import (
    HierarchicalChunker,
    deduplicate_chunks_by_level_text,
    embedding_text,
)
from paper_rag.config import Settings
from paper_rag.db import Database
from paper_rag.domain import SourcePaper
from paper_rag.embeddings import EmbeddingService
from paper_rag.parsers import ParserRegistry
from paper_rag.quality import assess_parsed_document
from paper_rag.repository import Repository, write_canonical_json
from paper_rag.text_utils import (
    normalize_doi,
    normalize_whitespace,
    sha256_file,
    validate_real_format,
)


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestionStats:
    total: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    lower_priority_skipped: int = 0


FORMAT_PRIORITY = {
    "application/pdf": 0,
    "application/xml": 1,
    "application/json": 2,
    "text/markdown": 3,
}


@dataclass(slots=True)
class PreparedCandidate:
    index: int
    row: dict[str, str]
    path: Path
    mime_type: str
    validation_warnings: list[str]


def _relative_path(raw_path: str, paper_root: Path) -> str:
    try:
        return Path(raw_path).resolve().relative_to(paper_root.resolve()).as_posix()
    except (ValueError, OSError):
        raw_windows = PureWindowsPath(raw_path)
        root_windows = PureWindowsPath(str(paper_root))
        try:
            return raw_windows.relative_to(root_windows).as_posix()
        except ValueError:
            return raw_windows.name


def _source_paper(row: dict[str, str], path: Path, csv_path: Path) -> SourcePaper:
    known = {
        "time", "title", "journal_type", "sub_journal", "doi",
        "status", "source", "file", "error", "csv_file",
    }
    metadata = {key: value for key, value in row.items() if key not in known and value}
    return SourcePaper(
        title=(row.get("title") or "").strip(),
        doi=normalize_doi(row.get("doi")),
        journal_type=(row.get("journal_type") or "").strip(),
        journal=(row.get("sub_journal") or "").strip(),
        file_path=path,
        source=(row.get("source") or "").strip(),
        downloaded_at=(row.get("time") or "").strip(),
        source_csv=(row.get("csv_file") or str(csv_path)).strip(),
        metadata=metadata,
    )


def _resolve_file_path(raw_path: str, csv_path: Path, paper_root: Path) -> Path:
    path = Path(raw_path)
    if path.exists() or path.is_absolute():
        return path
    from_root = paper_root / path
    if from_root.exists():
        return from_root
    return csv_path.parent / path


class IngestionPipeline:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        self.parsers = ParserRegistry(settings.grobid_url, settings.request_timeout_seconds)
        self.chunker = HierarchicalChunker(
            settings.parent_chunk_tokens,
            settings.child_chunk_tokens,
            settings.child_chunk_overlap,
        )
        self.embedder = EmbeddingService(
            settings.embedding_model,
            settings.embedding_device,
            settings.embedding_batch_size,
        )

    def ingest_csv(self, csv_path: Path, limit: int | None = None, force: bool = False) -> IngestionStats:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"title", "doi", "status", "file"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV缺少必需列: {', '.join(sorted(missing))}")
            rows = list(reader)
        stats = IngestionStats(total=len(rows))
        candidates = self._select_preferred_candidates(rows, csv_path, stats)
        if limit is not None:
            candidates = candidates[:limit]
        job_id = uuid4()
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO ingestion_jobs (job_id, source_csv, total_rows) VALUES (%s, %s, %s)",
                (job_id, str(csv_path), stats.total),
            )
            connection.commit()

        for index, candidate in enumerate(candidates, start=1):
            stats.processed += 1
            try:
                if self._ingest_one(csv_path, candidate, force):
                    stats.succeeded += 1
                else:
                    stats.skipped += 1
            except Exception as exc:
                stats.failed += 1
                logger.exception(
                    "[%s/%s] %s 处理失败: %s",
                    index,
                    len(candidates),
                    candidate.row.get("doi"),
                    exc,
                )
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE ingestion_jobs SET finished_at=now(), status=%s, processed_rows=%s,
                    success_rows=%s, failed_rows=%s, skipped_rows=%s
                WHERE job_id=%s
                """,
                (
                    "completed_with_errors" if stats.failed else "completed",
                    stats.processed, stats.succeeded, stats.failed, stats.skipped, job_id,
                ),
            )
            connection.commit()
        return stats

    def _select_preferred_candidates(
        self,
        rows: list[dict[str, str]],
        csv_path: Path,
        stats: IngestionStats,
    ) -> list[PreparedCandidate]:
        grouped: dict[str, list[PreparedCandidate]] = {}
        for index, row in enumerate(rows):
            if (row.get("status") or "").strip().lower() != "success":
                stats.skipped += 1
                continue
            raw_path = (row.get("file") or "").strip()
            if not raw_path:
                stats.failed += 1
                logger.warning("第%s行status=success但file为空", index + 2)
                continue
            path = _resolve_file_path(raw_path, csv_path, self.settings.paper_root)
            try:
                if not path.is_file():
                    raise FileNotFoundError(path)
                mime_type, warnings = validate_real_format(path)
            except Exception as exc:
                stats.failed += 1
                logger.warning("第%s行文件不可用，跳过: %s", index + 2, exc)
                continue
            doi = normalize_doi(row.get("doi"))
            title = normalize_whitespace(row.get("title") or "").casefold()
            journal = normalize_whitespace(row.get("sub_journal") or "").casefold()
            if doi:
                paper_key = f"doi:{doi}"
            elif title:
                paper_key = f"title:{title}|journal:{journal}"
            else:
                paper_key = f"file:{index}:{path}"
            candidate = PreparedCandidate(index, row, path, mime_type, warnings)
            grouped.setdefault(paper_key, []).append(candidate)

        selected: list[PreparedCandidate] = []
        for values in grouped.values():
            values.sort(key=lambda value: (FORMAT_PRIORITY[value.mime_type], value.index))
            selected.append(values[0])
            discarded = len(values) - 1
            stats.lower_priority_skipped += discarded
            stats.skipped += discarded
        selected.sort(key=lambda value: value.index)
        return selected

    def _ingest_one(
        self,
        csv_path: Path,
        candidate: PreparedCandidate,
        force: bool,
    ) -> bool:
        row = candidate.row
        path = candidate.path
        mime_type = candidate.mime_type
        validation_warnings = candidate.validation_warnings
        file_hash = sha256_file(path)
        source = _source_paper(row, path, csv_path)
        relative_path = _relative_path(str(path), self.settings.paper_root)

        with self.database.connection() as connection:
            repository = Repository(connection)
            paper_id = repository.upsert_paper(source)
            document_id, parse_status = repository.register_document(
                paper_id,
                path,
                relative_path,
                mime_type,
                file_hash,
                validation_warnings,
            )
            connection.commit()

        if parse_status == "embedded" and not force:
            logger.info("%s 已完成，跳过", source.doi or source.title)
            return False

        try:
            parser = self.parsers.get(path, mime_type)
            document = parser.parse(path)
            if not document.title:
                document.title = source.title
            if validation_warnings:
                document.warnings.extend(validation_warnings)
            if not document.sections:
                raise ValueError("解析结果没有可用章节")
            document.warnings.extend(assess_parsed_document(document))

            chunks = self.chunker.chunk(document)
            chunks, duplicate_chunks = deduplicate_chunks_by_level_text(chunks)
            if duplicate_chunks:
                logger.warning(
                    "%s chunk去重跳过 %s 个同级重复块",
                    source.doi or source.title,
                    duplicate_chunks,
                )
            child_chunks = [chunk for chunk in chunks if chunk.level == "child"]
            if not child_chunks:
                raise ValueError("没有生成可Embedding的子块")
            child_texts = [embedding_text(source.title, chunk) for chunk in child_chunks]
            child_vectors = self.embedder.encode_documents(child_texts)
            if self.embedder.dimension != self.settings.embedding_dimension:
                raise ValueError(
                    f"模型实际维度{self.embedder.dimension}与配置"
                    f"{self.settings.embedding_dimension}不一致"
                )
            child_embeddings = {
                chunk.chunk_id: vector for chunk, vector in zip(child_chunks, child_vectors, strict=True)
            }
            paper_vector = self.embedder.encode_documents(
                [f"Title: {source.title}\nAbstract: {document.abstract}"]
            )[0]

            canonical_path = self.settings.canonical_root / str(paper_id) / f"{document_id}.json"
            write_canonical_json(canonical_path, document)

            with self.database.connection() as connection:
                repository = Repository(connection)
                repository.save_parsed_document(
                    paper_id,
                    document_id,
                    document,
                    str(canonical_path),
                    chunks,
                    child_embeddings,
                    paper_vector,
                    self.settings.embedding_model,
                    self.settings.embedding_dimension,
                    self.chunker,
                )
                connection.commit()
            return True
        except Exception as exc:
            with self.database.connection() as connection:
                Repository(connection).mark_document_failed(document_id, str(exc))
                connection.commit()
            raise
