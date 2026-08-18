CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS papers (
    paper_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doi TEXT,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL DEFAULT '',
    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
    journal_type TEXT NOT NULL DEFAULT '',
    journal TEXT NOT NULL DEFAULT '',
    publication_date DATE,
    article_type TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'en',
    download_source TEXT NOT NULL DEFAULT '',
    downloaded_at TIMESTAMPTZ,
    source_csv TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS papers_doi_unique
ON papers (lower(doi)) WHERE doi IS NOT NULL AND doi <> '';

CREATE TABLE IF NOT EXISTS documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    original_path TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_format TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    file_sha256 TEXT NOT NULL UNIQUE,
    parse_status TEXT NOT NULL DEFAULT 'pending',
    parser_name TEXT NOT NULL DEFAULT '',
    parser_version TEXT NOT NULL DEFAULT '',
    parse_quality TEXT NOT NULL DEFAULT '',
    fulltext_status TEXT NOT NULL DEFAULT 'unknown',
    canonical_path TEXT NOT NULL DEFAULT '',
    text_length BIGINT NOT NULL DEFAULT 0,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS documents_paper_idx ON documents (paper_id);
CREATE INDEX IF NOT EXISTS documents_parse_status_idx ON documents (parse_status);

CREATE TABLE IF NOT EXISTS document_versions (
    document_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    canonical_path TEXT NOT NULL DEFAULT '',
    quality TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, content_hash, parser_name, parser_version)
);

CREATE TABLE IF NOT EXISTS sections (
    section_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID NOT NULL REFERENCES document_versions(document_version_id) ON DELETE CASCADE,
    section_order INTEGER NOT NULL,
    section_type TEXT NOT NULL,
    section_title TEXT NOT NULL,
    parent_title TEXT,
    page_start INTEGER,
    page_end INTEGER,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (document_version_id, section_order, content_hash)
);

CREATE INDEX IF NOT EXISTS sections_document_version_idx ON sections (document_version_id);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id UUID PRIMARY KEY,
    paper_id UUID NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    document_version_id UUID NOT NULL REFERENCES document_versions(document_version_id) ON DELETE CASCADE,
    parent_chunk_id UUID REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    chunk_level TEXT NOT NULL CHECK (chunk_level IN ('parent', 'child')),
    section_order INTEGER NOT NULL,
    section_type TEXT NOT NULL,
    section_title TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    text_hash TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(section_title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(content, '')), 'B')
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_version_id, chunk_level, text_hash, chunker_version)
);

CREATE INDEX IF NOT EXISTS chunks_paper_idx ON chunks (paper_id);
CREATE INDEX IF NOT EXISTS chunks_parent_idx ON chunks (parent_chunk_id);
CREATE INDEX IF NOT EXISTS chunks_search_gin_idx ON chunks USING GIN (search_vector);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id UUID NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT '',
    dimension INTEGER NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, model_name, model_version)
);

CREATE INDEX IF NOT EXISTS chunk_embeddings_hnsw_idx
ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS paper_embeddings (
    paper_id UUID NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT '',
    dimension INTEGER NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (paper_id, model_name, model_version)
);

CREATE INDEX IF NOT EXISTS paper_embeddings_hnsw_idx
ON paper_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_csv TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    total_rows INTEGER NOT NULL DEFAULT 0,
    processed_rows INTEGER NOT NULL DEFAULT 0,
    success_rows INTEGER NOT NULL DEFAULT 0,
    failed_rows INTEGER NOT NULL DEFAULT 0,
    skipped_rows INTEGER NOT NULL DEFAULT 0,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
