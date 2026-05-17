import sqlite3
from collections.abc import Iterator

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.jobs.repository import get_discovery_job
from app.main import app
from app.sources import DiscoveredUrl, SourceRegistry, create_discovered_url, create_source
from app.storage.database import get_connection, initialize_database


def test_create_jobs_from_discovered_urls_creates_jobs(tmp_path) -> None:
    db_path = tmp_path / "discovered_url_create_jobs.db"
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
                SourceRegistry(
                    source_name="Source", source_type="website", base_url="https://a.com"
                ),
            )
            url_1 = create_discovered_url(
                connection,
                DiscoveredUrl(
                    source_id=source.source_id,
                    url="https://a.com/p/1",
                    discovery_type="sitemap",
                    status="discovered",
                ),
            )
            url_2 = create_discovered_url(
                connection,
                DiscoveredUrl(
                    source_id=source.source_id,
                    url="https://a.com/p/2",
                    discovery_type="sitemap",
                    status="discovered",
                ),
            )

        client = TestClient(app)
        response = client.post(f"/sources/{source.source_id}/discovered-urls/create-jobs", json={})

        assert response.status_code == 200
        payload = response.json()
        assert payload["created_count"] == 2
        assert payload["skipped_count"] == 0
        assert len(payload["job_ids"]) == 2

        with get_connection(str(db_path)) as connection:
            jobs = [get_discovery_job(connection, job_id) for job_id in payload["job_ids"]]

        inputs = {url_1.url, url_2.url}
        for job in jobs:
            assert job is not None
            assert job.job_type.value == "url_extraction"
            assert job.status.value == "pending"
            assert job.input_type == "url"
            assert job.input_value in inputs
    finally:
        app.dependency_overrides.clear()


def test_create_jobs_from_discovered_urls_respects_status_filter(tmp_path) -> None:
    db_path = tmp_path / "discovered_url_create_jobs_filter.db"
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
                SourceRegistry(
                    source_name="Source", source_type="website", base_url="https://a.com"
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
            processed = create_discovered_url(
                connection,
                DiscoveredUrl(
                    source_id=source.source_id,
                    url="https://a.com/p/2",
                    discovery_type="sitemap",
                    status="processed",
                ),
            )

        client = TestClient(app)
        response = client.post(
            f"/sources/{source.source_id}/discovered-urls/create-jobs",
            json={"status": "processed", "limit": 50},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["created_count"] == 1

        with get_connection(str(db_path)) as connection:
            job = get_discovery_job(connection, payload["job_ids"][0])
        assert job is not None
        assert job.input_value == processed.url
    finally:
        app.dependency_overrides.clear()


def test_create_jobs_from_discovered_urls_respects_limit(tmp_path) -> None:
    db_path = tmp_path / "discovered_url_create_jobs_limit.db"
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
                SourceRegistry(
                    source_name="Source", source_type="website", base_url="https://a.com"
                ),
            )
            for i in range(3):
                create_discovered_url(
                    connection,
                    DiscoveredUrl(
                        source_id=source.source_id,
                        url=f"https://a.com/p/{i}",
                        discovery_type="sitemap",
                        status="discovered",
                    ),
                )

        client = TestClient(app)
        response = client.post(
            f"/sources/{source.source_id}/discovered-urls/create-jobs", json={"limit": 1}
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["created_count"] == 1
        assert len(payload["job_ids"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_create_jobs_from_discovered_urls_missing_source_returns_404(tmp_path) -> None:
    db_path = tmp_path / "discovered_url_create_jobs_missing.db"
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
        response = client.post("/sources/missing/discovered-urls/create-jobs", json={})

        assert response.status_code == 404
        assert "Source not found" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_create_jobs_from_discovered_urls_empty_source_returns_zero(tmp_path) -> None:
    db_path = tmp_path / "discovered_url_create_jobs_empty.db"
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
                SourceRegistry(
                    source_name="Source", source_type="website", base_url="https://a.com"
                ),
            )

        client = TestClient(app)
        response = client.post(f"/sources/{source.source_id}/discovered-urls/create-jobs", json={})

        assert response.status_code == 200
        payload = response.json()
        assert payload["created_count"] == 0
        assert payload["job_ids"] == []
    finally:
        app.dependency_overrides.clear()


def test_create_jobs_from_discovered_urls_invalid_url_is_skipped(tmp_path) -> None:
    db_path = tmp_path / "discovered_url_create_jobs_invalid.db"
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
                SourceRegistry(
                    source_name="Source", source_type="website", base_url="https://a.com"
                ),
            )
            create_discovered_url(
                connection,
                DiscoveredUrl(
                    source_id=source.source_id,
                    url="not-a-url",
                    discovery_type="sitemap",
                    status="discovered",
                ),
            )

        client = TestClient(app)
        response = client.post(f"/sources/{source.source_id}/discovered-urls/create-jobs", json={})

        assert response.status_code == 200
        payload = response.json()
        assert payload["created_count"] == 0
        assert payload["skipped_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_create_jobs_from_discovered_urls_passes_batch_and_priority(tmp_path) -> None:
    db_path = tmp_path / "discovered_url_create_jobs_batch_priority.db"
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
                SourceRegistry(
                    source_name="Source", source_type="website", base_url="https://a.com"
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
        response = client.post(
            f"/sources/{source.source_id}/discovered-urls/create-jobs",
            json={"priority": "high", "batch_id": "batch-1"},
        )

        assert response.status_code == 200
        payload = response.json()
        with get_connection(str(db_path)) as connection:
            job = get_discovery_job(connection, payload["job_ids"][0])

        assert job is not None
        assert job.priority.value == "high"
        assert job.batch_id == "batch-1"
    finally:
        app.dependency_overrides.clear()
