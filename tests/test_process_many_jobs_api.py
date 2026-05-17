import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection, get_discovery_job_processor
from app.jobs.models import DiscoveryJob, JobPriority, JobStatus, JobType
from app.main import app
from app.storage.database import get_connection, initialize_database


def _override_db(db_path: str) -> Callable[[], Iterator[sqlite3.Connection]]:
    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(db_path)
        try:
            yield connection
        finally:
            connection.close()

    return override_get_db_connection


def _make_job(job_id: str) -> DiscoveryJob:
    now = datetime.now(UTC)
    return DiscoveryJob(
        job_id=job_id,
        job_type=JobType.url_extraction,
        status=JobStatus.completed,
        priority=JobPriority.normal,
        input_type="url",
        input_value=f"https://example.test/{job_id}",
        created_at=now,
        updated_at=now,
        result_product_id=f"prod-{job_id}",
    )


def test_process_many_jobs_processes_multiple_jobs(tmp_path) -> None:
    db_path = tmp_path / "jobs_api_many.db"
    initialize_database(str(db_path))

    def fake_processor(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        del connection
        return _make_job(job_id)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: fake_processor
    try:
        client = TestClient(app)
        response = client.post(
            "/jobs/process-many", json={"job_ids": ["job-1", "job-2"], "max_jobs": 10}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_count"] == 2
    assert payload["processed_count"] == 2
    assert payload["skipped_count"] == 0
    assert len(payload["results"]) == 2


def test_process_many_jobs_caps_processing_by_max_jobs(tmp_path) -> None:
    db_path = tmp_path / "jobs_api_many.db"
    initialize_database(str(db_path))

    def fake_processor(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        del connection
        return _make_job(job_id)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: fake_processor
    try:
        client = TestClient(app)
        response = client.post(
            "/jobs/process-many",
            json={"job_ids": ["job-1", "job-2", "job-3"], "max_jobs": 2},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["processed_count"] == 2
    assert payload["skipped_count"] == 1
    assert len(payload["results"]) == 2


def test_process_many_jobs_returns_not_found_item(tmp_path) -> None:
    db_path = tmp_path / "jobs_api_many.db"
    initialize_database(str(db_path))

    def fake_processor(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        del connection
        if job_id == "missing-job":
            return None
        return _make_job(job_id)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: fake_processor
    try:
        client = TestClient(app)
        response = client.post(
            "/jobs/process-many", json={"job_ids": ["ok-job", "missing-job"], "max_jobs": 10}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    not_found_item = next(item for item in payload["results"] if item["job_id"] == "missing-job")
    assert not_found_item["status"] == "not_found"
    assert "Discovery job not found" in not_found_item["error_message"]


def test_process_many_jobs_value_error_becomes_failed_item(tmp_path) -> None:
    db_path = tmp_path / "jobs_api_many.db"
    initialize_database(str(db_path))

    def fake_processor(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        del connection
        if job_id == "bad-job":
            raise ValueError("invalid job type")
        return _make_job(job_id)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: fake_processor
    try:
        client = TestClient(app)
        response = client.post(
            "/jobs/process-many", json={"job_ids": ["ok-job", "bad-job"], "max_jobs": 10}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    failed_item = next(item for item in payload["results"] if item["job_id"] == "bad-job")
    assert failed_item["status"] == "failed"
    assert failed_item["error_message"] is not None


def test_process_many_jobs_empty_job_ids_returns_422(tmp_path) -> None:
    db_path = tmp_path / "jobs_api_many.db"
    initialize_database(str(db_path))

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    try:
        client = TestClient(app)
        response = client.post("/jobs/process-many", json={"job_ids": [], "max_jobs": 10})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_process_many_jobs_max_jobs_over_limit_returns_422(tmp_path) -> None:
    db_path = tmp_path / "jobs_api_many.db"
    initialize_database(str(db_path))

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    try:
        client = TestClient(app)
        response = client.post("/jobs/process-many", json={"job_ids": ["job-1"], "max_jobs": 21})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_process_many_jobs_route_ordering_hits_bulk_endpoint(tmp_path) -> None:
    db_path = tmp_path / "jobs_api_many.db"
    initialize_database(str(db_path))

    def fake_processor(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        del connection
        return _make_job(job_id)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: fake_processor
    try:
        client = TestClient(app)
        response = client.post(
            "/jobs/process-many", json={"job_ids": ["job-1"], "max_jobs": 10}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "requested_count" in response.json()
