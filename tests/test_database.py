import sqlite3
from pathlib import Path

from app.storage import ensure_database_directory, get_connection, initialize_database


def test_ensure_database_directory_creates_parent(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "data" / "app.db"

    ensure_database_directory(str(db_path))

    assert db_path.parent.exists()


def test_initialize_database_creates_file(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "product_discover_agent.db"

    initialize_database(str(db_path))

    assert db_path.exists()


def test_initialize_database_creates_required_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "product_discover_agent.db"
    initialize_database(str(db_path))

    expected_tables = {"products", "product_evidence", "discovery_jobs", "batch_jobs"}

    with get_connection(str(db_path)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    created_tables = {row["name"] for row in rows}
    assert expected_tables.issubset(created_tables)


def test_get_connection_uses_dict_like_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "rows.db"

    with get_connection(str(db_path)) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute("INSERT INTO sample (name) VALUES (?)", ("demo",))
        row = connection.execute("SELECT id, name FROM sample").fetchone()

    assert isinstance(row, sqlite3.Row)
    assert row["name"] == "demo"


def test_initialize_database_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "product_discover_agent.db"

    initialize_database(str(db_path))
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        result = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    assert len(result) >= 4
