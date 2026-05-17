from collections.abc import Iterator

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.jobs.repository import get_discovery_job
from app.main import app
from app.storage.database import get_connection, initialize_database


def test_ingest_barcode_creates_job(tmp_path) -> None:
    db_path = tmp_path / "barcode_api.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        with get_connection(str(db_path)) as connection:
            yield connection

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.post(
            "/ingest/barcode",
            json={
                "barcode": " 3017-6204 22003 ",
                "priority": "high",
                "batch_id": "batch-xyz",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["job_type"] == "barcode_lookup"
    assert payload["status"] == "pending"
    assert payload["input_type"] == "barcode"
    assert payload["input_value"] == "3017620422003"
    assert payload["priority"] == "high"
    assert payload["batch_id"] == "batch-xyz"

    with get_connection(str(db_path)) as connection:
        job = get_discovery_job(connection, payload["job_id"])

    assert job is not None
    assert job.input_value == "3017620422003"


def test_ingest_barcode_rejects_invalid_barcode(tmp_path) -> None:
    db_path = tmp_path / "barcode_api.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        with get_connection(str(db_path)) as connection:
            yield connection

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.post("/ingest/barcode", json={"barcode": "abc-123"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "Invalid barcode" in response.json()["detail"]
