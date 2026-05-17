import sqlite3

import pytest

from app.storage.database import get_connection, initialize_database
from app.storage.orm_models import Base


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def test_initialize_database_creates_source_discovery_tables(tmp_path) -> None:
    db_path = tmp_path / "source_discovery.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        assert _table_exists(connection, "source_registry")
        assert _table_exists(connection, "discovered_urls")
        assert _table_exists(connection, "extraction_runs")


def test_source_registry_accepts_insert(tmp_path) -> None:
    db_path = tmp_path / "source_discovery.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO source_registry (
                source_id, source_name, source_type, base_url,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "source-1",
                "Open Food Facts",
                "open_database",
                "https://world.openfoodfacts.org",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()
        count = connection.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]

    assert count == 1


def test_discovered_urls_accepts_insert_and_enforces_url_hash_uniqueness(tmp_path) -> None:
    db_path = tmp_path / "source_discovery.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO discovered_urls (
                url_id, source_id, url, url_hash, discovery_type, status,
                barcode, product_id, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "url-1",
                "source-1",
                "https://example.com/product/3017620422003",
                "hash-1",
                "seed",
                "pending",
                "3017620422003",
                None,
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()

        count = connection.execute("SELECT COUNT(*) FROM discovered_urls").fetchone()[0]
        assert count == 1

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO discovered_urls (
                    url_id, source_id, url, url_hash, discovery_type, status,
                    barcode, product_id, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "url-2",
                    "source-1",
                    "https://example.com/product/another",
                    "hash-1",
                    "seed",
                    "pending",
                    None,
                    None,
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )


def test_extraction_runs_accepts_insert(tmp_path) -> None:
    db_path = tmp_path / "source_discovery.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO extraction_runs (
                run_id, source_id, status, started_at, completed_at,
                pages_seen, products_found, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1",
                "source-1",
                "completed",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T01:00:00+00:00",
                25,
                4,
                None,
            ),
        )
        connection.commit()
        count = connection.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0]

    assert count == 1


def test_initialize_database_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "source_discovery.db"
    initialize_database(str(db_path))
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        assert _table_exists(connection, "source_registry")
        assert _table_exists(connection, "discovered_urls")
        assert _table_exists(connection, "extraction_runs")


def test_orm_metadata_includes_source_discovery_tables() -> None:
    table_names = set(Base.metadata.tables.keys())
    assert "source_registry" in table_names
    assert "discovered_urls" in table_names
    assert "extraction_runs" in table_names
