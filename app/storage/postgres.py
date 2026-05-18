"""PostgreSQL storage foundation helpers."""

import psycopg
from psycopg.rows import dict_row


def get_postgres_connection(database_url: str) -> psycopg.Connection:
    """Create and return a psycopg connection."""
    if not database_url or not database_url.strip():
        raise ValueError("database_url must be a non-empty string")

    return psycopg.connect(database_url, row_factory=dict_row)


def initialize_postgres_database(database_url: str, schema_sql: str) -> None:
    """Initialize PostgreSQL schema from SQL text."""
    connection = get_postgres_connection(database_url)
    try:
        connection.execute(schema_sql)
        connection.commit()
    finally:
        connection.close()
