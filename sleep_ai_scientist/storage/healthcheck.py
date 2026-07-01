from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

from sleep_ai_scientist.storage.db import create_engine_from_config, database_url_from_config, load_config, mask_database_url


def check_database_connection(config_path: str | Path | None = None, *, backend: str | None = None) -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    path = config_path or "configs/database_config.yaml"
    try:
        config = load_config(path)
        selected, url = database_url_from_config(config, backend=backend)
        engine = create_engine_from_config(path, backend=backend)
        with engine.connect() as conn:
            conn.execute(text("select 1"))
            table_count = len(inspect(conn).get_table_names())
        engine.dispose()
        return {
            "ok": True,
            "backend": selected,
            "database_url_masked": mask_database_url(url),
            "table_count": table_count,
            "checked_at": checked_at,
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "backend": backend or "",
            "database_url_masked": "",
            "table_count": 0,
            "checked_at": checked_at,
            "error": str(exc),
        }

