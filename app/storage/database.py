import sqlite3
from pathlib import Path

from app.storage.schema import CREATE_TABLES_SQL


def get_connection(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_database_directory(database_path: str) -> None:
    path = Path(database_path)
    if path.parent and str(path.parent) != ".":
        path.parent.mkdir(parents=True, exist_ok=True)


def initialize_database(database_path: str) -> None:
    ensure_database_directory(database_path)
    with get_connection(database_path) as connection:
        connection.executescript(CREATE_TABLES_SQL)
        connection.commit()
