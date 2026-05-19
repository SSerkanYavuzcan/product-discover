import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.main import app
from app.sources.models import ExtractionRun, SourceRegistry
from app.sources.repository import create_source
from app.storage.database import get_connection, initialize_database


def test_discover_sitemap_endpoint_returns_run_and_passes_params(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "sitemap_api.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        source = create_source(
            connection,
            SourceRegistry(
                source_name="Demo Market",
                source_type="website",
                base_url="https://demo.example.com",
            ),
        )

    captured: dict[str, object] = {}

    def fake_discover_urls_from_source_sitemap(
        connection: sqlite3.Connection,
        source_id: str,
        fetcher=None,
        max_child_sitemaps: int = 5,
        product_only: bool = True,
    ) -> ExtractionRun | None:
        captured["source_id"] = source_id
        captured["max_child_sitemaps"] = max_child_sitemaps
        captured["product_only"] = product_only
        return ExtractionRun(
            run_id="run-123",
            source_id=source_id,
            status="completed",
            started_at=datetime.now(UTC),
            pages_seen=14,
            products_found=9,
        )

    monkeypatch.setattr(
        "app.api.routes.discover_urls_from_source_sitemap",
        fake_discover_urls_from_source_sitemap,
    )

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection

    try:
        client = TestClient(app)

        response = client.post(
            f"/sources/{source.source_id}/discover-sitemap",
            json={"max_sitemaps": 2, "product_only": False},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["run_id"] == "run-123"
        assert payload["source_id"] == source.source_id
        assert payload["status"] == "completed"
        assert payload["pages_seen"] == 14
        assert payload["products_found"] == 9

        assert captured["source_id"] == source.source_id
        assert captured["max_child_sitemaps"] == 2
        assert captured["product_only"] is False
    finally:
        app.dependency_overrides.clear()


def test_discover_sitemap_endpoint_404_when_source_missing(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "missing_source_api.db"
    initialize_database(str(db_path))

    def fake_discover_urls_from_source_sitemap(
        connection: sqlite3.Connection,
        source_id: str,
        fetcher=None,
        max_child_sitemaps: int = 5,
        product_only: bool = True,
    ) -> ExtractionRun | None:
        return None

    monkeypatch.setattr(
        "app.api.routes.discover_urls_from_source_sitemap",
        fake_discover_urls_from_source_sitemap,
    )

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection

    try:
        client = TestClient(app)
        response = client.post("/sources/missing-source/discover-sitemap", json={})
        assert response.status_code == 404
        assert "Source not found" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_discover_sitemap_endpoint_uses_default_payload_values(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "defaults_api.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        source = create_source(
            connection,
            SourceRegistry(
                source_name="Default Market",
                source_type="website",
                base_url="https://default.example.com",
            ),
        )

    captured: dict[str, object] = {}

    def fake_discover_urls_from_source_sitemap(
        connection: sqlite3.Connection,
        source_id: str,
        fetcher=None,
        max_child_sitemaps: int = 5,
        product_only: bool = True,
    ) -> ExtractionRun | None:
        captured["max_child_sitemaps"] = max_child_sitemaps
        captured["product_only"] = product_only
        return ExtractionRun(
            run_id="run-defaults",
            source_id=source_id,
            status="completed",
            started_at=datetime.now(UTC),
            pages_seen=0,
            products_found=0,
        )

    monkeypatch.setattr(
        "app.api.routes.discover_urls_from_source_sitemap",
        fake_discover_urls_from_source_sitemap,
    )

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection

    try:
        client = TestClient(app)
        response = client.post(f"/sources/{source.source_id}/discover-sitemap", json={})
        assert response.status_code == 200
        assert captured["max_child_sitemaps"] == 5
        assert captured["product_only"] is True
    finally:
        app.dependency_overrides.clear()


def test_discover_sitemap_endpoint_rejects_negative_max_child_sitemaps(tmp_path) -> None:
    db_path = tmp_path / "validation_api.db"
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
        response = client.post(
            "/sources/any-source/discover-sitemap",
            json={"max_child_sitemaps": -1, "product_only": True},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_discover_sitemap_endpoint_accepts_legacy_and_new_limits(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "limits_api.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        source = create_source(
            connection,
            SourceRegistry(
                source_name="Limits Market",
                source_type="website",
                base_url="https://limits.example.com",
            ),
        )

    captured: dict[str, object] = {}

    def fake_discover_urls_from_source_sitemap(
        connection,
        source_id,
        fetcher=None,
        max_child_sitemaps=5,
        product_only=True,
    ):
        captured["max_child_sitemaps"] = max_child_sitemaps
        return ExtractionRun(
            run_id="run-limits",
            source_id=source_id,
            status="completed",
            started_at=datetime.now(UTC),
            pages_seen=0,
            products_found=0,
        )

    monkeypatch.setattr(
        "app.api.routes.discover_urls_from_source_sitemap",
        fake_discover_urls_from_source_sitemap,
    )

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.post(
            f"/sources/{source.source_id}/discover-sitemap",
            json={"max_child_sitemaps": 120},
        )
        assert response.status_code == 200
        assert captured["max_child_sitemaps"] == 120
    finally:
        app.dependency_overrides.clear()
