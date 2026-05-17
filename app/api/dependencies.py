import sqlite3
from collections.abc import Iterator

from app.config import get_settings
from app.storage.database import get_connection, initialize_database


def get_db_connection() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    initialize_database(settings.database_path)

    connection = get_connection(settings.database_path)
    try:
        yield connection
    finally:
        connection.close()
