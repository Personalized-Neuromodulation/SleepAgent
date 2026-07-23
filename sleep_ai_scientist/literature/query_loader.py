from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_yaml
from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.storage.repositories import QueryRepository


@dataclass(frozen=True)
class LiteratureQuery:
    query_id: str
    query_text: str
    query_group: str
    query_set_version: str
    priority: float = 1.0


def select_query_payload(payload: dict[str, Any], scope: str | None = None) -> dict[str, Any]:
    query_sets = payload.get("query_sets")
    if not query_sets:
        return payload
    selected_scope = scope or "library"
    if selected_scope not in query_sets:
        available = ", ".join(sorted(str(key) for key in query_sets))
        raise KeyError(f"Query scope '{selected_scope}' not found. Available scopes: {available}")
    selected = dict(query_sets[selected_scope] or {})
    selected.setdefault("scope", selected_scope)
    return selected


def load_query_set(path: str | Path, scope: str | None = None) -> tuple[dict[str, Any], list[LiteratureQuery]]:
    payload = select_query_payload(read_yaml(Path(path)), scope=scope)
    version = payload.get("query_set", {}).get("version", "")
    queries: list[LiteratureQuery] = []
    seen: set[tuple[str, str]] = set()
    for group, values in payload.get("queries", {}).items():
        for query_text in values or []:
            key = (str(group), str(query_text))
            if key in seen:
                continue
            seen.add(key)
            queries.append(
                LiteratureQuery(
                    query_id=stable_id("query", version, group, query_text),
                    query_text=str(query_text),
                    query_group=str(group),
                    query_set_version=str(version),
                    priority=1.0,
                )
            )
    return payload, queries


def write_queries_to_db(session, queries: list[LiteratureQuery]) -> list[LiteratureQuery]:  # type: ignore[no-untyped-def]
    repo = QueryRepository()
    for item in queries:
        repo.upsert_query(session, item.query_text, item.query_group, item.query_set_version, priority=item.priority)
    return queries
