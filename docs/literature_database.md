# Literature Metadata Database

`Literature` is the document-management subsystem. A `Paper` is one globally
deduplicated canonical publication within that subsystem. Python models live in
`sleep_ai_scientist.literature_db`; PostgreSQL tables use the `literature_`
prefix, and the CLI group is `literature-db`.

This subsystem is PostgreSQL-only and contains metadata tables for update runs,
candidates, canonical papers, ordered paper authors, identifiers, discovery
sources, abstract versions, deduplication decisions, paper relations, and
journal crawling. Journal crawling stores public metadata only; it does not
download PDFs or restricted full text and does not implement chunking,
embeddings, or RAG.

The project reads database settings in this order:

1. Current process environment variables.
2. The project-root `.env` file.
3. Non-secret YAML settings.
4. A clear error when the PostgreSQL URL is missing.

Use the local test configuration with these commands:

```bash
python -m sleep_ai_scientist.cli literature-db check-db \
  --config configs/literature_database_test.yaml
python -m sleep_ai_scientist.cli literature-db rebuild-schema \
  --config configs/literature_database_test.yaml
python -m sleep_ai_scientist.cli literature-db schema-status \
  --config configs/literature_database_test.yaml
```

`rebuild-schema` drops only the application database named in the configured
URL, recreates it with UTF-8 encoding, and creates the Literature Metadata and
journal-crawl tables. It refuses to rebuild `postgres`, `template0`, or
`template1`.

Target-journal discovery always plans every valid, deduplicated row in
`data/external/2025_Q1_IF_5.csv` unless `--limit-journals` is explicitly used for
debugging. The normal workflow is:

```bash
python -m sleep_ai_scientist.cli literature-db resolve-journal-urls \
  --config configs/literature_database_test.yaml --all
python -m sleep_ai_scientist.cli literature-db build-journal-profiles \
  --config configs/literature_database_test.yaml --all
python -m sleep_ai_scientist.cli literature-db crawl-all-journals \
  --config configs/literature_database_test.yaml --resume
python -m sleep_ai_scientist.cli literature-db crawl-all-journals \
  --config configs/literature_database_test.yaml --access-failures-only \
  --sample-one-article-per-journal
python -m sleep_ai_scientist.cli literature-db crawl-all-journals \
  --config configs/literature_database.yaml --web-search-audit-all \
  --sample-one-article-per-journal
python -m sleep_ai_scientist.cli literature-db journal-scan-status \
  --config configs/literature_database_test.yaml
```

The crawler checks and caches `robots.txt` per domain, supports `*` and `$`
robots rules, uses a shared domain rate limiter, and obeys `Retry-After`.
Publisher-owned feeds and article listings are tried directly for robots/403
homepage failures. Crossref is disabled in the default request policy and is
never used to relabel a robots/403 failure as a successful website crawl.
