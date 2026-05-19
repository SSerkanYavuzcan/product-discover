import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection, get_discovery_job_processor
from app.jobs.models import DiscoveryJob, JobPriority, JobStatus, JobType
from app.main import app
from app.sources import DiscoveredUrl, SourceRegistry, create_discovered_url, create_source
from app.storage.database import get_connection, initialize_database


def _override_db(db_path: str) -> Callable[[], Iterator[sqlite3.Connection]]:
    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(db_path)
        try:
            yield connection
        finally:
            connection.close()

    return override_get_db_connection


def _job(job_id: str, status: JobStatus) -> DiscoveryJob:
    now = datetime.now(UTC)
    return DiscoveryJob(
        job_id=job_id,
        job_type=JobType.url_extraction,
        status=status,
        priority=JobPriority.normal,
        input_type="url",
        input_value=f"https://example.test/{job_id}",
        created_at=now,
        updated_at=now,
    )


def test_processing_summary_returns_counts(tmp_path) -> None:
    db_path = tmp_path / "source_summary.db"
    initialize_database(str(db_path))
    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    try:
        with get_connection(str(db_path)) as connection:
            source = create_source(
                connection,
                SourceRegistry(source_name="S", source_type="website", base_url="https://a.com"),
            )
            statuses = [
                "discovered",
                "queued",
                "running",
                "completed",
                "processed",
                "failed",
                "not_found",
            ]
            for index, status in enumerate(statuses):
                create_discovered_url(
                    connection,
                    DiscoveredUrl(
                        source_id=source.source_id,
                        url=f"https://a.com/p/{index}",
                        discovery_type="sitemap",
                        status=status,
                        product_id="prod-1" if status in {"completed", "processed"} else None,
                    ),
                )

        response = TestClient(app).get(f"/sources/{source.source_id}/processing-summary")
        assert response.status_code == 200
        payload = response.json()
        assert payload["discovered_urls"] == 1
        assert payload["queued_urls"] == 1
        assert payload["running_urls"] == 1
        assert payload["completed_urls"] == 2
        assert payload["failed_urls"] == 1
        assert payload["not_found_urls"] == 1
        assert payload["remaining_urls"] == 1
        assert payload["total_urls"] == 7
        assert payload["total_products"] == 1
    finally:
        app.dependency_overrides.clear()


def test_process_next_batch_respects_batch_size_and_empty_behavior(tmp_path) -> None:
    db_path = tmp_path / "source_batch_size.db"
    initialize_database(str(db_path))

    def fake_processor(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        del connection
        return _job(job_id, JobStatus.completed)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: fake_processor
    try:
        with get_connection(str(db_path)) as connection:
            source = create_source(
                connection,
                SourceRegistry(source_name="S", source_type="website", base_url="https://a.com"),
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
        first = client.post(
            f"/sources/{source.source_id}/process-next-batch", json={"batch_size": 2}
        )
        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["created_count"] == 2
        assert first_payload["processed_count"] == 2

        second = client.post(
            f"/sources/{source.source_id}/process-next-batch", json={"batch_size": 2}
        )
        assert second.status_code == 200
        second_payload = second.json()
        assert second_payload["created_count"] == 1

        third = client.post(
            f"/sources/{source.source_id}/process-next-batch", json={"batch_size": 2}
        )
        assert third.status_code == 200
        third_payload = third.json()
        assert third_payload["created_count"] == 0
        assert third_payload["remaining_urls"] == 0
    finally:
        app.dependency_overrides.clear()


def test_process_next_batch_size_over_limit_returns_422(tmp_path) -> None:
    db_path = tmp_path / "source_batch_limit.db"
    initialize_database(str(db_path))
    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    try:
        response = TestClient(app).post(
            "/sources/missing/process-next-batch", json={"batch_size": 21}
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_process_next_batch_mixed_results_counts_and_missing_source(tmp_path) -> None:
    db_path = tmp_path / "source_batch_mixed.db"
    initialize_database(str(db_path))

    call_count = {"value": 0}

    def fake_processor(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        del connection
        index = call_count["value"]
        call_count["value"] += 1
        if index == 0:
            return _job(job_id, JobStatus.completed)
        if index == 1:
            return _job(job_id, JobStatus.failed)
        return _job(job_id, JobStatus.not_found)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: fake_processor
    try:
        with get_connection(str(db_path)) as connection:
            source = create_source(
                connection,
                SourceRegistry(source_name="S", source_type="website", base_url="https://a.com"),
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
        payload = client.post(
            f"/sources/{source.source_id}/process-next-batch", json={"batch_size": 3}
        ).json()
        assert payload["completed_count"] == 1
        assert payload["failed_count"] == 2
        assert payload["not_found_count"] == 1

        missing = client.get("/sources/missing/processing-summary")
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
