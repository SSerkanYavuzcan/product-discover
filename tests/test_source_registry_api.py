import sqlite3
from collections.abc import Iterator

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.main import app
from app.storage.database import get_connection, initialize_database


def test_post_sources_returns_201_and_source_id(tmp_path) -> None:
    temp_db_path = str(tmp_path / "sources_api.db")
    initialize_database(temp_db_path)

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(temp_db_path)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.post(
            "/sources",
            json={
                "source_name": "Open Food Facts",
                "source_type": "open_database",
                "base_url": "https://world.openfoodfacts.org",
                "country": "FR",
                "language": "fr",
                "priority": 10,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_id"]


def test_get_source_by_id_and_missing(tmp_path) -> None:
    temp_db_path = str(tmp_path / "sources_api.db")
    initialize_database(temp_db_path)

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(temp_db_path)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        created = client.post(
            "/sources",
            json={
                "source_name": "Source A",
                "source_type": "retailer",
                "base_url": "https://example.com",
            },
        ).json()

        found = client.get(f"/sources/{created['source_id']}")
        missing = client.get("/sources/missing-source")
    finally:
        app.dependency_overrides.clear()

    assert found.status_code == 200
    assert found.json()["source_id"] == created["source_id"]
    assert missing.status_code == 404


def test_get_sources_active_only_and_patch_active(tmp_path) -> None:
    temp_db_path = str(tmp_path / "sources_api.db")
    initialize_database(temp_db_path)

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(temp_db_path)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        active = client.post(
            "/sources",
            json={
                "source_name": "Active Source",
                "source_type": "brand_site",
                "base_url": "https://active.example.com",
            },
        ).json()

        inactive = client.post(
            "/sources",
            json={
                "source_name": "Inactive Source",
                "source_type": "brand_site",
                "base_url": "https://inactive.example.com",
                "is_active": False,
            },
        ).json()

        listed = client.get("/sources")
        patched = client.patch(f"/sources/{active['source_id']}/active", json={"is_active": False})
        listed_after = client.get("/sources")
        missing_patch = client.patch("/sources/missing-source/active", json={"is_active": True})
    finally:
        app.dependency_overrides.clear()

    assert listed.status_code == 200
    listed_ids = [item["source_id"] for item in listed.json()]
    assert active["source_id"] in listed_ids
    assert inactive["source_id"] not in listed_ids

    assert patched.status_code == 200
    assert patched.json()["is_active"] is False

    listed_after_ids = [item["source_id"] for item in listed_after.json()]
    assert active["source_id"] not in listed_after_ids

    assert missing_patch.status_code == 404
