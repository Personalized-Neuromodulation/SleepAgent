from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector
from psycopg import Connection
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, database_url: str, min_size: int = 1, max_size: int = 8):
        self.database_url = database_url
        self.pool = ConnectionPool(
            conninfo=database_url,
            min_size=min_size,
            max_size=max_size,
            configure=register_vector,
            open=False,
        )

    def open(self) -> None:
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        with self.pool.connection() as connection:
            yield connection

    def initialize(self, schema_path: Path) -> None:
        # Registering vector before CREATE EXTENSION can fail on a brand-new database,
        # so bootstrap with a one-off plain connection first.
        with psycopg.connect(self.database_url) as connection:
            connection.execute(schema_path.read_text(encoding="utf-8"))
            connection.commit()

