import sqlite3
from collections.abc import Iterator

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.main import app
from app.storage.database import get_connection, initialize_database


def test_source_registry_api_flow(tmp_path) -> None:
    db_path = tmp_path / "source_registry_api.db"
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

        create_response = client.post(
            "/sources",
            json={
                "source_name": "Demo Market",
                "source_type": "website",
                "base_url": "https://demo.example.com",
                "country": "US",
                "language": "en",
                "priority": 10,
                "is_active": True,
            },
        )
        assert create_response.status_code == 201
        created_payload = create_response.json()
        assert created_payload["source_id"]
        assert created_payload["source_name"] == "Demo Market"
        assert created_payload["source_type"] == "website"
        assert created_payload["base_url"] == "https://demo.example.com"
        assert created_payload["country"] == "US"
        assert created_payload["language"] == "en"
        assert created_payload["priority"] == 10
        assert created_payload["is_active"] is True

        source_id = created_payload["source_id"]

        get_response = client.get(f"/sources/{source_id}")
        assert get_response.status_code == 200
        fetched_payload = get_response.json()
        assert fetched_payload["source_id"] == source_id
        assert fetched_payload["source_name"] == "Demo Market"

        missing_get_response = client.get("/sources/missing-source")
        assert missing_get_response.status_code == 404
        assert missing_get_response.json()["detail"] == "Source not found: missing-source"

        inactive_create_response = client.post(
            "/sources",
            json={
                "source_name": "Dormant Source",
                "source_type": "website",
                "base_url": "https://inactive.example.com",
                "is_active": False,
            },
        )
        assert inactive_create_response.status_code == 201

        list_response = client.get("/sources")
        assert list_response.status_code == 200
        listed_sources = list_response.json()
        listed_ids = {source["source_id"] for source in listed_sources}
        assert source_id in listed_ids
        assert inactive_create_response.json()["source_id"] not in listed_ids

        deactivate_response = client.patch(
            f"/sources/{source_id}/active",
            json={"is_active": False},
        )
        assert deactivate_response.status_code == 200
        assert deactivate_response.json()["is_active"] is False

        list_after_deactivate = client.get("/sources")
        assert list_after_deactivate.status_code == 200
        listed_after_deactivate = {source["source_id"] for source in list_after_deactivate.json()}
        assert source_id not in listed_after_deactivate

        missing_patch_response = client.patch(
            "/sources/missing-source/active",
            json={"is_active": True},
        )
        assert missing_patch_response.status_code == 404
        assert missing_patch_response.json()["detail"] == "Source not found: missing-source"
    finally:
        app.dependency_overrides.clear()
