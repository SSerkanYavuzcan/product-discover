import sqlite3

from app.storage.database import initialize_database


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def test_initialize_database_creates_source_discovery_tables(tmp_path) -> None:
    db_path = tmp_path / "source_discovery_schema.db"
    initialize_database(str(db_path))

    with sqlite3.connect(db_path) as connection:
        assert _table_exists(connection, "source_registry")
        assert _table_exists(connection, "discovered_urls")
        assert _table_exists(connection, "extraction_runs")


def test_source_registry_accepts_insert(tmp_path) -> None:
    db_path = tmp_path / "source_discovery_schema.db"
    initialize_database(str(db_path))

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO source_registry (
                source_id, source_name, source_type, base_url, country, language,
                is_active, priority, crawl_frequency_hours, robots_policy, notes,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "src-1",
                "Open Food Facts",
                "open_database",
                "https://world.openfoodfacts.org",
                "US",
                "en",
                1,
                100,
                24,
                "respect",
                "seed",
                "2026-05-17T00:00:00+00:00",
                "2026-05-17T00:00:00+00:00",
            ),
        )
        connection.commit()

        row = connection.execute(
            "SELECT source_id, source_name FROM source_registry WHERE source_id = ?",
            ("src-1",),
        ).fetchone()
        assert row is not None
        assert row[0] == "src-1"


def test_discovered_urls_url_hash_uniqueness_is_enforced(tmp_path) -> None:
    db_path = tmp_path / "source_discovery_schema.db"
    initialize_database(str(db_path))

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO discovered_urls (
                url_id, source_id, url, url_hash, discovery_type, status,
                barcode, product_id, first_seen_at, last_seen_at, last_checked_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "url-1",
                "src-1",
                "https://example.com/p/1",
                "hash-1",
                "seed",
                "pending",
                None,
                None,
                "2026-05-17T00:00:00+00:00",
                "2026-05-17T00:00:00+00:00",
                None,
                None,
            ),
        )
        connection.commit()

        try:
            connection.execute(
                """
                INSERT INTO discovered_urls (
                    url_id, source_id, url, url_hash, discovery_type, status,
                    barcode, product_id, first_seen_at, last_seen_at, last_checked_at, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "url-2",
                    "src-1",
                    "https://example.com/p/2",
                    "hash-1",
                    "seed",
                    "pending",
                    None,
                    None,
                    "2026-05-17T00:00:00+00:00",
                    "2026-05-17T00:00:00+00:00",
                    None,
                    None,
                ),
            )
            connection.commit()
            raise AssertionError("Expected UNIQUE constraint to reject duplicate url_hash")
        except sqlite3.IntegrityError:
            pass


def test_initialize_database_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "source_discovery_schema.db"

    initialize_database(str(db_path))
    initialize_database(str(db_path))

    with sqlite3.connect(db_path) as connection:
        assert _table_exists(connection, "source_registry")
        assert _table_exists(connection, "discovered_urls")
        assert _table_exists(connection, "extraction_runs")
