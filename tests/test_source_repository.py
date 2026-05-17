import hashlib
import sqlite3

import pytest

from app.sources import (
    DiscoveredUrl,
    ExtractionRun,
    SourceRegistry,
    compute_url_hash,
    create_discovered_url,
    create_extraction_run,
    create_source,
    get_discovered_url_by_hash,
    get_source,
    list_active_sources,
    update_discovered_url_status,
    update_extraction_run_status,
    update_source_active_status,
)
from app.storage.database import get_connection, initialize_database


def _ensure_source_discovery_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_registry (
            source_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            base_url TEXT NOT NULL,
            country TEXT,
            language TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            priority INTEGER NOT NULL DEFAULT 100,
            crawl_frequency_hours INTEGER,
            robots_policy TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS discovered_urls (
            url_id TEXT PRIMARY KEY,
            source_id TEXT,
            url TEXT NOT NULL,
            url_hash TEXT NOT NULL UNIQUE,
            discovery_type TEXT NOT NULL,
            status TEXT NOT NULL,
            barcode TEXT,
            product_id TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_checked_at TEXT,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS extraction_runs (
            run_id TEXT PRIMARY KEY,
            source_id TEXT,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            pages_seen INTEGER NOT NULL DEFAULT 0,
            products_found INTEGER NOT NULL DEFAULT 0,
            error_message TEXT
        );
        """
    )
    connection.commit()


def test_compute_url_hash_is_deterministic() -> None:
    url = "https://example.com/product/1"
    assert compute_url_hash(url) == compute_url_hash(url)


def test_compute_url_hash_normalizes_whitespace_and_casing() -> None:
    normalized = "https://example.com/product/1"
    expected = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    assert compute_url_hash("  HTTPS://EXAMPLE.COM/PRODUCT/1  ") == expected


def test_create_and_get_source(tmp_path) -> None:
    db_path = tmp_path / "sources.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        _ensure_source_discovery_tables(connection)
        created = create_source(
            connection,
            SourceRegistry(
                source_name="Open Food Facts",
                source_type="open_database",
                base_url="https://world.openfoodfacts.org",
            ),
        )
        fetched = get_source(connection, created.source_id or "")

    assert created.source_id is not None
    assert fetched is not None
    assert fetched.source_name == "Open Food Facts"


def test_get_source_returns_none_for_missing(tmp_path) -> None:
    db_path = tmp_path / "sources.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        _ensure_source_discovery_tables(connection)
        assert get_source(connection, "missing") is None


def test_list_active_sources_ordered_by_priority_then_name(tmp_path) -> None:
    db_path = tmp_path / "sources.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        _ensure_source_discovery_tables(connection)
        create_source(
            connection,
            SourceRegistry(
                source_name="B Source",
                source_type="type",
                base_url="https://b",
                priority=20,
            ),
        )
        create_source(
            connection,
            SourceRegistry(
                source_name="A Source",
                source_type="type",
                base_url="https://a",
                priority=10,
            ),
        )
        create_source(
            connection,
            SourceRegistry(
                source_name="Inactive",
                source_type="type",
                base_url="https://i",
                priority=1,
                is_active=False,
            ),
        )
        active = list_active_sources(connection)

    assert [source.source_name for source in active] == ["A Source", "B Source"]


def test_update_source_active_status_deactivates_source(tmp_path) -> None:
    db_path = tmp_path / "sources.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        _ensure_source_discovery_tables(connection)
        created = create_source(
            connection,
            SourceRegistry(source_name="Src", source_type="type", base_url="https://src"),
        )
        updated = update_source_active_status(connection, created.source_id or "", False)

    assert updated is not None
    assert updated.is_active is False


def test_create_discovered_url_and_get_by_hash(tmp_path) -> None:
    db_path = tmp_path / "sources.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        _ensure_source_discovery_tables(connection)
        created = create_discovered_url(
            connection,
            DiscoveredUrl(
                source_id="src-1",
                url="https://example.com/p/123",
                discovery_type="seed",
                status="pending",
            ),
        )
        fetched = get_discovered_url_by_hash(connection, created.url_hash or "")

    assert created.url_id is not None
    assert created.url_hash == compute_url_hash("https://example.com/p/123")
    assert fetched is not None
    assert fetched.url == "https://example.com/p/123"


def test_duplicate_url_hash_raises_integrity_error(tmp_path) -> None:
    db_path = tmp_path / "sources.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        _ensure_source_discovery_tables(connection)
        create_discovered_url(
            connection,
            DiscoveredUrl(url="https://example.com/p/123", discovery_type="seed", status="pending"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            create_discovered_url(
                connection,
                DiscoveredUrl(
                    url=" HTTPS://EXAMPLE.COM/P/123 ",
                    discovery_type="seed",
                    status="pending",
                ),
            )


def test_update_discovered_url_status_updates_fields(tmp_path) -> None:
    db_path = tmp_path / "sources.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        _ensure_source_discovery_tables(connection)
        created = create_discovered_url(
            connection,
            DiscoveredUrl(url="https://example.com/p/123", discovery_type="seed", status="pending"),
        )
        updated = update_discovered_url_status(
            connection,
            created.url_id or "",
            status="processed",
            error_message="none",
            product_id="prod-1",
            barcode="123456",
        )

    assert updated is not None
    assert updated.status == "processed"
    assert updated.error_message == "none"
    assert updated.product_id == "prod-1"
    assert updated.barcode == "123456"
    assert updated.last_checked_at is not None


def test_create_and_update_extraction_run(tmp_path) -> None:
    db_path = tmp_path / "sources.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        _ensure_source_discovery_tables(connection)
        created = create_extraction_run(
            connection,
            ExtractionRun(source_id="src-1", status="running"),
        )
        updated = update_extraction_run_status(
            connection,
            created.run_id or "",
            status="completed",
            pages_seen=12,
            products_found=3,
            error_message="ok",
            mark_completed=True,
        )

    assert created.run_id is not None
    assert updated is not None
    assert updated.status == "completed"
    assert updated.pages_seen == 12
    assert updated.products_found == 3
    assert updated.error_message == "ok"
    assert updated.completed_at is not None


def test_update_functions_return_none_for_missing_ids(tmp_path) -> None:
    db_path = tmp_path / "sources.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        _ensure_source_discovery_tables(connection)
        source = update_source_active_status(connection, "missing", True)
        url = update_discovered_url_status(connection, "missing", status="processed")
        run = update_extraction_run_status(connection, "missing", status="completed")

    assert source is None
    assert url is None
    assert run is None
