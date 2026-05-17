from collections.abc import Iterator

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.ingestion.url import is_valid_url, normalize_url
from app.jobs.repository import get_discovery_job
from app.main import app
from app.storage.database import get_connection, initialize_database


def test_normalize_url_strips_whitespace() -> None:
    assert normalize_url("  https://example.com/p  ") == "https://example.com/p"


def test_is_valid_url_accepts_https() -> None:
    assert is_valid_url("https://example.com/product") is True


def test_is_valid_url_accepts_http() -> None:
    assert is_valid_url("http://example.com/product") is True


def test_is_valid_url_rejects_missing_scheme() -> None:
    assert is_valid_url("example.com/product") is False


def test_is_valid_url_rejects_unsupported_scheme() -> None:
    assert is_valid_url("ftp://example.com/product") is False


def test_post_ingest_url_creates_pending_url_extraction_job(tmp_path) -> None:
    db_path = tmp_path / "url_ingestion.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        with get_connection(str(db_path)) as connection:
            yield connection

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.post(
            "/ingest/url",
            json={
                "url": "  https://example.com/product-page  ",
                "priority": "high",
                "batch_id": "batch-123",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["job_type"] == "url_extraction"
    assert payload["status"] == "pending"
    assert payload["input_type"] == "url"
    assert payload["input_value"] == "https://example.com/product-page"
    assert payload["priority"] == "high"
    assert payload["batch_id"] == "batch-123"

    with get_connection(str(db_path)) as connection:
        job = get_discovery_job(connection, payload["job_id"])

    assert job is not None
    assert job.job_type.value == "url_extraction"


def test_post_ingest_url_returns_400_for_invalid_url(tmp_path) -> None:
    db_path = tmp_path / "url_ingestion.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        with get_connection(str(db_path)) as connection:
            yield connection

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.post("/ingest/url", json={"url": "not-a-url"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "Invalid URL" in response.json()["detail"]
