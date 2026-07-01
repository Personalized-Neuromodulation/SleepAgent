from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from sleep_ai_scientist.common.config import load_config, project_root, resolve_path
from sleep_ai_scientist.storage.models import Base


def _bool_env(name: str | None, default: bool = False) -> bool:
    if not name:
        return default
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def database_url_from_config(config: dict[str, Any], *, backend: str | None = None) -> tuple[str, str]:
    db_cfg = config.get("database", {})
    selected = backend or os.getenv(db_cfg.get("backend_env", ""), db_cfg.get("default_backend", "sqlite"))
    root = Path(config.get("_project_root", project_root()))
    if selected == "postgresql":
        url = os.getenv(db_cfg.get("url_env", ""), "")
        if url:
            return selected, url
        fallback = config.get("sqlite_fallback", {})
        if fallback.get("enabled_for_local_dev", True):
            selected = "sqlite"
        else:
            raise ValueError("PostgreSQL selected but database URL is missing")
    if selected == "sqlite":
        sqlite_path = os.getenv(db_cfg.get("sqlite_path_env", ""), db_cfg.get("default_sqlite_path", "data/literature/sleep_literature.db"))
        return selected, f"sqlite:///{resolve_path(sqlite_path, root)}"
    raise ValueError(f"Unsupported database backend: {selected}")


def mask_database_url(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    prefix, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    auth, host = rest.split("@", 1)
    user = auth.split(":", 1)[0]
    return f"{prefix}://{user}:***@{host}"


def create_engine_from_config(config_path: str | Path = "configs/database_config.yaml", *, backend: str | None = None) -> Engine:
    config = load_config(config_path)
    db_cfg = config.get("database", {})
    selected, url = database_url_from_config(config, backend=backend)
    echo = _bool_env(db_cfg.get("echo_env"), False)
    kwargs: dict[str, Any] = {"echo": echo, "future": True}
    if selected == "postgresql":
        kwargs["pool_pre_ping"] = bool(db_cfg.get("pool_pre_ping", True))
        kwargs["pool_recycle"] = int(db_cfg.get("pool_recycle_seconds", 1800))
    engine = create_engine(url, **kwargs)
    if selected == "sqlite":
        Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    return engine


def init_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session_factory = make_session_factory(engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

