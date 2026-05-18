from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.storage.database import get_connection, initialize_database
from app.storage.database_url import (
    normalize_database_backend,
    require_database_url_for_postgres,
)
from app.storage.postgres import get_postgres_connection
from app.storage.postgres_adapter import PostgresConnectionAdapter
from app.storage.schema import CREATE_TABLES_SQL


@contextmanager
def get_runtime_connection(
    *,
    database_backend: str,
    database_path: str,
    database_url: str | None,
) -> Iterator[sqlite3.Connection | PostgresConnectionAdapter]:
    backend = normalize_database_backend(database_backend)

    if backend == "sqlite":
        initialize_database(database_path)
        connection = get_connection(database_path)
        try:
            yield connection
        finally:
            connection.close()
        return

    required_database_url = require_database_url_for_postgres(backend, database_url)
    raw_connection = get_postgres_connection(required_database_url)
    connection = PostgresConnectionAdapter(raw_connection)
    try:
        connection.executescript(CREATE_TABLES_SQL)
        connection.commit()
        yield connection
    finally:
        connection.close()
