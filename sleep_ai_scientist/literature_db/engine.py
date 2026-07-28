from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from .config import env_bool, load_literature_db_config
from .models import Base


def database_settings(config_path: str | Path) -> tuple[dict, URL, str]:
    config = load_literature_db_config(config_path)
    database = config.get("database", {})
    backend = os.getenv("SLEEPAGENT_DATABASE_BACKEND", database.get("backend"))
    if backend != "postgresql":
        raise ValueError(
            "Literature Database requires PostgreSQL; alternative backends are unsupported"
        )
    url_env = database.get("url_env", "SLEEPAGENT_DATABASE_URL")
    raw_url = os.getenv(url_env)
    if not raw_url:
        raise ValueError(f"Required PostgreSQL URL is missing: set {url_env}")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError(
            "Literature Database requires PostgreSQL; alternative backends are unsupported"
        )
    if not url.database:
        raise ValueError("PostgreSQL application database name is missing from the URL")
    return config, url, database.get("schema", "public")


def create_database_engine(
    config_path: str | Path,
    *,
    url: str | URL | None = None,
    require_postgresql: bool = True,
) -> Engine:
    config, configured_url, schema = database_settings(config_path)
    selected_url = make_url(url) if url is not None else configured_url
    if selected_url.get_backend_name() != "postgresql":
        raise ValueError("This operation requires PostgreSQL; alternative backends are unsupported")
    database = config.get("database", {})
    connect_args = {}
    if schema != "public":
        connect_args["options"] = f"-csearch_path={schema}"
    return create_engine(
        selected_url,
        echo=env_bool("SLEEPAGENT_DB_ECHO", bool(database.get("echo", False))),
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def init_database(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        raise ValueError("Literature Database schema can only be created in PostgreSQL")
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session = sessionmaker(engine, expire_on_commit=False, future=True)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
