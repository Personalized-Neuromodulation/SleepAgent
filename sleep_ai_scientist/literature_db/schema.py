from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, URL

from sleep_ai_scientist.common.config import environment_value_source

from .engine import create_database_engine, database_settings, init_database


EXPECTED_TABLES = (
    "literature_update_runs",
    "literature_candidates",
    "literature_papers",
    "literature_paper_authors",
    "literature_paper_identifiers",
    "literature_paper_sources",
    "literature_abstract_versions",
    "literature_dedup_decisions",
    "literature_paper_relations",
    "literature_journal_scan_states",
    "literature_journal_urls",
    "literature_journal_scraper_profiles",
    "literature_journal_crawl_runs",
)
SYSTEM_DATABASES = {"postgres", "template0", "template1"}


def masked_url(url: URL) -> str:
    return url.render_as_string(hide_password=True)


def check_database(config_path: str | Path) -> dict[str, Any]:
    _, url, schema = database_settings(config_path)
    engine = create_database_engine(config_path)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT 1, current_database(), current_schema(), version(), "
                    "inet_server_addr()::text, inet_server_port()"
                )
            ).one()
        return {
            "backend": "postgresql",
            "url_source": environment_value_source("SLEEPAGENT_DATABASE_URL"),
            "url": masked_url(url),
            "connection": "ok" if row[0] == 1 else "failed",
            "database": row[1],
            "schema": row[2] or schema,
            "postgresql_version": row[3],
            "host": url.host or row[4],
            "port": url.port or row[5],
        }
    finally:
        engine.dispose()


def _application_tables(engine: Engine, schema: str) -> list[str]:
    return sorted(inspect(engine).get_table_names(schema=schema))


def rebuild_database(config_path: str | Path) -> dict[str, Any]:
    _, url, schema = database_settings(config_path)
    database_name = url.database
    if not database_name or database_name in SYSTEM_DATABASES:
        raise ValueError(f"Refusing to rebuild protected database: {database_name!r}")

    before_engine = create_database_engine(config_path)
    try:
        removed_tables = _application_tables(before_engine, schema)
    finally:
        before_engine.dispose()

    admin_url = url.set(database="postgres")
    admin_engine = create_engine(
        admin_url, future=True, isolation_level="AUTOCOMMIT", pool_pre_ping=True
    )
    quoted_database = admin_engine.dialect.identifier_preparer.quote(database_name)
    owner = url.username
    try:
        with admin_engine.connect() as connection:
            terminated = connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = :database AND pid <> pg_backend_pid()"
                ),
                {"database": database_name},
            ).scalar_one()
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database AND pid <> pg_backend_pid()"
                ),
                {"database": database_name},
            )
            connection.execute(text(f"DROP DATABASE {quoted_database}"))
            owner_clause = ""
            if owner:
                quoted_owner = admin_engine.dialect.identifier_preparer.quote(owner)
                owner_clause = f" OWNER {quoted_owner}"
            connection.execute(
                text(
                    f"CREATE DATABASE {quoted_database}{owner_clause} "
                    "ENCODING 'UTF8' TEMPLATE template0"
                )
            )
    finally:
        admin_engine.dispose()

    engine = create_database_engine(config_path)
    try:
        if schema != "public":
            quoted_schema = engine.dialect.identifier_preparer.quote(schema)
            with engine.begin() as connection:
                connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema}"))
        init_database(engine)
        actual_tables = _application_tables(engine, schema)
    finally:
        engine.dispose()
    return {
        "database": database_name,
        "schema": schema,
        "terminated_connections": terminated,
        "database_dropped": True,
        "database_created": True,
        "encoding": "UTF8",
        "removed_tables": removed_tables,
        "created_tables": actual_tables,
        "success": actual_tables == sorted(EXPECTED_TABLES),
    }


def schema_status(config_path: str | Path) -> dict[str, Any]:
    _, url, schema = database_settings(config_path)
    engine = create_database_engine(config_path)
    expected = sorted(EXPECTED_TABLES)
    try:
        inspector = inspect(engine)
        actual = sorted(inspector.get_table_names(schema=schema))
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        quote = engine.dialect.identifier_preparer.quote
        row_counts: dict[str, int] = {}
        constraints: dict[str, Any] = {}
        indexes: dict[str, Any] = {}
        with engine.connect() as connection:
            for table in actual:
                row_counts[table] = connection.execute(
                    text(f"SELECT count(*) FROM {quote(schema)}.{quote(table)}")
                ).scalar_one()
                constraints[table] = {
                    "primary_key": inspector.get_pk_constraint(table, schema=schema),
                    "unique": inspector.get_unique_constraints(table, schema=schema),
                    "check": inspector.get_check_constraints(table, schema=schema),
                    "foreign_keys": inspector.get_foreign_keys(table, schema=schema),
                }
                indexes[table] = inspector.get_indexes(table, schema=schema)
        required_indexes = {
            "uq_literature_abstract_versions_preferred",
            "uq_literature_dedup_decisions_current",
        }
        found_indexes = {
            item["name"] for table_indexes in indexes.values() for item in table_indexes
        }
        key_indexes_ok = required_indexes <= found_indexes
        overall = not missing and not unexpected and key_indexes_ok
        return {
            "database": url.database,
            "schema": schema,
            "expected_tables": expected,
            "actual_tables": actual,
            "missing_tables": missing,
            "unexpected_tables": unexpected,
            "row_counts": row_counts,
            "key_constraints": constraints,
            "key_indexes": indexes,
            "required_partial_indexes_present": key_indexes_ok,
            "overall_schema_status": "pass" if overall else "fail",
        }
    finally:
        engine.dispose()
