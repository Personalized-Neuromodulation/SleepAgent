from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from psycopg import Connection
from psycopg.types.json import Jsonb

from paper_rag.chunking import HierarchicalChunker
from paper_rag.domain import Chunk, ParsedDocument, SourcePaper
from paper_rag.text_utils import normalize_doi, sha256_text


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None


def _parse_date(value: Any) -> date | None:
    match = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", str(value or "").strip())
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2) or 1), int(match.group(3) or 1))
    except ValueError:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Repository:
    def __init__(self, connection: Connection):
        self.connection = connection

    def _executemany(self, query: str, rows: list[tuple[Any, ...]]) -> None:
            if not rows:
                return
            with self.connection.cursor() as cursor:
                cursor.executemany(query, rows)

    def upsert_paper(self, source: SourcePaper) -> UUID:
        doi = normalize_doi(source.doi)
        if doi:
            row = self.connection.execute(
                "SELECT paper_id FROM papers WHERE lower(doi) = lower(%s)", (doi,)
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT paper_id FROM papers
                WHERE lower(title) = lower(%s) AND lower(journal) = lower(%s)
                ORDER BY created_at LIMIT 1
                """,
                (source.title, source.journal),
            ).fetchone()
        if row:
            paper_id = row[0]
            self.connection.execute(
                """
                UPDATE papers SET
                    title = %s,
                    journal_type = %s,
                    journal = %s,
                    download_source = %s,
                    downloaded_at = COALESCE(%s, downloaded_at),
                    source_csv = %s,
                    metadata = metadata || %s,
                    updated_at = now()
                WHERE paper_id = %s
                """,
                (
                    source.title,
                    source.journal_type,
                    source.journal,
                    source.source,
                    _parse_timestamp(source.downloaded_at),
                    source.source_csv,
                    Jsonb(source.metadata),
                    paper_id,
                ),
            )
            return paper_id

        paper_id = uuid4()
        self.connection.execute(
            """
            INSERT INTO papers (
                paper_id, doi, title, journal_type, journal,
                download_source, downloaded_at, source_csv, metadata
            ) VALUES (%s, NULLIF(%s, ''), %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                paper_id,
                doi,
                source.title,
                source.journal_type,
                source.journal,
                source.source,
                _parse_timestamp(source.downloaded_at),
                source.source_csv,
                Jsonb(source.metadata),
            ),
        )
        return paper_id

    def register_document(
        self,
        paper_id: UUID,
        path: Path,
        relative_path: str,
        mime_type: str,
        file_hash: str,
        validation_warnings: list[str],
    ) -> tuple[UUID, str]:
        existing = self.connection.execute(
            "SELECT document_id, parse_status FROM documents WHERE file_sha256 = %s",
            (file_hash,),
        ).fetchone()
        if existing:
            return existing[0], existing[1]
        document_id = uuid4()
        self.connection.execute(
            """
            INSERT INTO documents (
                document_id, paper_id, original_path, relative_path,
                file_format, mime_type, file_size, file_sha256, warnings
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                document_id,
                paper_id,
                str(path),
                relative_path,
                {
                    "application/pdf": "pdf",
                    "application/xml": "xml",
                    "application/json": "json",
                    "text/markdown": "md",
                }.get(mime_type, path.suffix.lower().lstrip(".")),
                mime_type,
                path.stat().st_size,
                file_hash,
                Jsonb(validation_warnings),
            ),
        )
        return document_id, "pending"

    def save_parsed_document(
        self,
        paper_id: UUID,
        document_id: UUID,
        document: ParsedDocument,
        canonical_path: str,
        chunks: list[Chunk],
        child_embeddings: dict[UUID, np.ndarray],
        paper_embedding: np.ndarray,
        embedding_model: str,
        embedding_dimension: int,
        chunker: HierarchicalChunker,
    ) -> UUID:
        content_hash = sha256_text("\n\n".join(section.text for section in document.sections))
        # A paper may have several downloaded representations. Preserve older
        # document versions for audit, but expose only the newly selected best format.
        self.connection.execute(
            """
            UPDATE document_versions AS version
            SET is_active = FALSE
            FROM documents AS document
            WHERE version.document_id = document.document_id
              AND document.paper_id = %s
            """,
            (paper_id,),
        )
        existing = self.connection.execute(
            """
            SELECT document_version_id FROM document_versions
            WHERE document_id = %s AND content_hash = %s
              AND parser_name = %s AND parser_version = %s
            """,
            (document_id, content_hash, document.parser_name, document.parser_version),
        ).fetchone()
        if existing:
            version_id = existing[0]
            self.connection.execute(
                "UPDATE document_versions SET is_active = TRUE WHERE document_version_id = %s",
                (version_id,),
            )
        else:
            version_id = uuid4()
            self.connection.execute(
                """
                INSERT INTO document_versions (
                    document_version_id, document_id, content_hash,
                    parser_name, parser_version, canonical_path,
                    quality, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    document_id,
                    content_hash,
                    document.parser_name,
                    document.parser_version,
                    canonical_path,
                    document.quality,
                    Jsonb(document.metadata),
                ),
            )

        self.connection.execute("DELETE FROM chunks WHERE document_version_id = %s", (version_id,))
        self.connection.execute("DELETE FROM sections WHERE document_version_id = %s", (version_id,))

        section_rows = [
            (
                uuid4(),
                version_id,
                section.order,
                section.section_type,
                section.title,
                section.parent_title,
                section.page_start,
                section.page_end,
                section.text,
                sha256_text(section.text),
                Jsonb(section.metadata),
            )
            for section in document.sections
        ]
        self._executemany(
            """
            INSERT INTO sections (
                section_id, document_version_id, section_order, section_type,
                section_title, parent_title, page_start, page_end,
                content, content_hash, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            section_rows,
        )

        for level in ("parent", "child"):
            rows = [
                (
                    chunk.chunk_id,
                    paper_id,
                    version_id,
                    chunk.parent_chunk_id,
                    chunk.level,
                    chunk.section_order,
                    chunk.section_type,
                    chunk.section_title,
                    chunk.index,
                    chunk.page_start,
                    chunk.page_end,
                    chunk.text,
                    chunk.token_count,
                    chunk.text_hash,
                    chunker.version,
                    Jsonb(chunk.metadata),
                )
                for chunk in chunks
                if chunk.level == level
            ]
            if rows:
                self._executemany(
                    """
                    INSERT INTO chunks (
                        chunk_id, paper_id, document_version_id, parent_chunk_id,
                        chunk_level, section_order, section_type, section_title,
                        chunk_index, page_start, page_end, content, token_count,
                        text_hash, chunker_version, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )

        embedding_rows = [
            (
                chunk_id,
                embedding_model,
                "",
                embedding_dimension,
                vector,
            )
            for chunk_id, vector in child_embeddings.items()
        ]
        if embedding_rows:
            self._executemany(
                """
                INSERT INTO chunk_embeddings (
                    chunk_id, model_name, model_version, dimension, embedding
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (chunk_id, model_name, model_version)
                DO UPDATE SET embedding = EXCLUDED.embedding,
                              dimension = EXCLUDED.dimension,
                              created_at = now()
                """,
                embedding_rows,
            )

        self.connection.execute(
            """
            INSERT INTO paper_embeddings (
                paper_id, model_name, model_version, dimension, embedding
            ) VALUES (%s, %s, '', %s, %s)
            ON CONFLICT (paper_id, model_name, model_version)
            DO UPDATE SET embedding = EXCLUDED.embedding,
                          dimension = EXCLUDED.dimension,
                          created_at = now()
            """,
            (paper_id, embedding_model, embedding_dimension, paper_embedding),
        )

        parsed_title = document.title.strip()
        parsed_abstract = document.abstract.strip()
        authors = document.metadata.get("authors") or []
        publication_date = _parse_date(document.metadata.get("publication_date"))
        self.connection.execute(
            """
            UPDATE papers SET
                title = CASE WHEN title = '' THEN %s ELSE title END,
                abstract = CASE WHEN %s <> '' THEN %s ELSE abstract END,
                authors = CASE WHEN %s THEN %s ELSE authors END,
                publication_date = COALESCE(%s, publication_date),
                updated_at = now()
            WHERE paper_id = %s
            """,
            (
                parsed_title, parsed_abstract, parsed_abstract,
                bool(authors), Jsonb(authors), publication_date, paper_id,
            ),
        )
        self.connection.execute(
            """
            UPDATE documents SET
                parse_status = 'embedded', parser_name = %s, parser_version = %s,
                parse_quality = %s, fulltext_status = %s,
                canonical_path = %s, text_length = %s,
                warnings = %s, error = '', updated_at = now()
            WHERE document_id = %s
            """,
            (
                document.parser_name,
                document.parser_version,
                document.quality,
                "complete" if len(document.sections) >= 3 else "partial",
                canonical_path,
                sum(len(section.text) for section in document.sections),
                Jsonb(document.warnings),
                document_id,
            ),
        )
        return version_id

    def mark_document_failed(self, document_id: UUID, error: str) -> None:
        self.connection.execute(
            """
            UPDATE documents
            SET parse_status = 'failed', error = %s, updated_at = now()
            WHERE document_id = %s
            """,
            (error[:10_000], document_id),
        )


def canonical_json(document: ParsedDocument) -> dict[str, Any]:
    return {
        "title": document.title,
        "abstract": document.abstract,
        "parser": {"name": document.parser_name, "version": document.parser_version},
        "quality": document.quality,
        "warnings": document.warnings,
        "metadata": document.metadata,
        "sections": [
            {
                "title": section.title,
                "section_type": section.section_type,
                "order": section.order,
                "text": section.text,
                "page_start": section.page_start,
                "page_end": section.page_end,
                "parent_title": section.parent_title,
                "metadata": section.metadata,
            }
            for section in document.sections
        ],
        "assets": [
            {
                "asset_type": asset.asset_type,
                "label": asset.label,
                "caption": asset.caption,
                "page": asset.page,
                "content": asset.content,
            }
            for asset in document.assets
        ],
        "references": document.references,
    }


def write_canonical_json(path: Path, document: ParsedDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(canonical_json(document), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
