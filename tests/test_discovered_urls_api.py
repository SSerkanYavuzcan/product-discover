import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.main import app
from app.sources import (
    DiscoveredUrl,
    SourceRegistry,
    create_discovered_url,
    create_source,
    list_discovered_urls_by_source,
)
from app.storage.database import get_connection, initialize_database


def test_discovered_urls_api_returns_discovered_urls(tmp_path) -> None:
    db_path = tmp_path / "discovered_urls_api.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        with get_connection(str(db_path)) as connection:
            source = create_source(
                connection,
                SourceRegistry(source_name="Source", source_type="website", base_url="https://a.com"),
            )
            create_discovered_url(
                connection,
                DiscoveredUrl(
                    source_id=source.source_id,
                    url="https://a.com/p/2",
                    discovery_type="sitemap",
                    status="discovered",
                ),
            )
            create_discovered_url(
                connection,
                DiscoveredUrl(
                    source_id=source.source_id,
                    url="https://a.com/p/1",
                    discovery_type="sitemap",
                    status="discovered",
                ),
            )

        client = TestClient(app)
        response = client.get(f"/sources/{source.source_id}/discovered-urls")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 2
        assert {item["url"] for item in payload} == {"https://a.com/p/1", "https://a.com/p/2"}
        assert all(item["source_id"] == source.source_id for item in payload)
    finally:
        app.dependency_overrides.clear()


def test_discovered_urls_api_filters_by_status(tmp_path) -> None:
    db_path = tmp_path / "discovered_urls_filter.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        with get_connection(str(db_path)) as connection:
            source = create_source(
                connection,
                SourceRegistry(source_name="Source", source_type="website", base_url="https://a.com"),
            )
            create_discovered_url(
                connection,
                DiscoveredUrl(
                    source_id=source.source_id,
                    url="https://a.com/p/1",
                    discovery_type="sitemap",
                    status="discovered",
                ),
            )
            create_discovered_url(
                connection,
                DiscoveredUrl(
                    source_id=source.source_id,
                    url="https://a.com/p/2",
                    discovery_type="sitemap",
                    status="processed",
                ),
            )

        client = TestClient(app)
        response = client.get(f"/sources/{source.source_id}/discovered-urls?status=discovered")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["status"] == "discovered"
    finally:
        app.dependency_overrides.clear()


def test_discovered_urls_api_supports_limit_and_offset(tmp_path) -> None:
    db_path = tmp_path / "discovered_urls_limit_offset.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        with get_connection(str(db_path)) as connection:
            source = create_source(
                connection,
                SourceRegistry(source_name="Source", source_type="website", base_url="https://a.com"),
            )
            for index in range(3):
                create_discovered_url(
                    connection,
                    DiscoveredUrl(
                        source_id=source.source_id,
                        url=f"https://a.com/p/{index}",
                        discovery_type="sitemap",
                        status="discovered",
                    ),
                )

        client = TestClient(app)
        response = client.get(f"/sources/{source.source_id}/discovered-urls?limit=1&offset=1")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
    finally:
        app.dependency_overrides.clear()


def test_discovered_urls_api_missing_source_returns_404(tmp_path) -> None:
    db_path = tmp_path / "discovered_urls_missing.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get("/sources/missing/discovered-urls")

        assert response.status_code == 404
        assert "Source not found" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_discovered_urls_api_empty_source_returns_empty_list(tmp_path) -> None:
    db_path = tmp_path / "discovered_urls_empty.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        with get_connection(str(db_path)) as connection:
            source = create_source(
                connection,
                SourceRegistry(source_name="Source", source_type="website", base_url="https://a.com"),
            )

        client = TestClient(app)
        response = client.get(f"/sources/{source.source_id}/discovered-urls")

        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides.clear()


def test_list_discovered_urls_by_source_orders_and_filters(tmp_path) -> None:
    db_path = tmp_path / "discovered_urls_repo.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        source = create_source(
            connection,
            SourceRegistry(source_name="Source", source_type="website", base_url="https://a.com"),
        )
        seen_at = datetime(2026, 1, 1, tzinfo=UTC)
        create_discovered_url(
            connection,
            DiscoveredUrl(
                source_id=source.source_id,
                url="https://a.com/p/b",
                discovery_type="sitemap",
                status="discovered",
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            ),
        )
        create_discovered_url(
            connection,
            DiscoveredUrl(
                source_id=source.source_id,
                url="https://a.com/p/a",
                discovery_type="sitemap",
                status="discovered",
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            ),
        )
        create_discovered_url(
            connection,
            DiscoveredUrl(
                source_id=source.source_id,
                url="https://a.com/p/c",
                discovery_type="sitemap",
                status="processed",
            ),
        )

        discovered_rows = list_discovered_urls_by_source(
            connection,
            source.source_id or "",
            status="discovered",
        )

    assert [item.url for item in discovered_rows] == ["https://a.com/p/a", "https://a.com/p/b"]
