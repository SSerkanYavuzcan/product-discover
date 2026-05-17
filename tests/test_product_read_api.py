from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.main import app
from app.models import ProductProfile, SourceEvidence
from app.models.repository import add_product_evidence, create_product
from app.storage.database import get_connection, initialize_database


def test_get_product_by_id_returns_product(tmp_path) -> None:
    db_path = tmp_path / "product_read_api.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        with get_connection(str(db_path)) as connection:
            yield connection

    with get_connection(str(db_path)) as connection:
        created = create_product(
            connection,
            ProductProfile(
                product_id="prod-001",
                barcode="0123456789012",
                product_name="Hazelnut Spread",
                brand="Sample Brand",
                status="active",
            ),
        )
        add_product_evidence(
            connection,
            created.product_id or "",
            SourceEvidence(
                source_name="Open Food Facts",
                source_type="api",
                source_url="https://world.openfoodfacts.org/product/0123456789012",
                field_name="product_name",
                raw_value="Hazelnut Spread",
                normalized_value="Hazelnut Spread",
                confidence=0.9,
                extracted_at=datetime.now(UTC),
            ),
        )

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get(f"/products/{created.product_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["product_id"] == created.product_id
    assert payload["barcode"] == "0123456789012"
    assert payload["product_name"] == "Hazelnut Spread"
    assert payload["brand"] == "Sample Brand"
    assert len(payload["evidence"]) >= 1


def test_get_product_by_id_returns_404_for_missing_product(tmp_path) -> None:
    db_path = tmp_path / "product_read_api.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        with get_connection(str(db_path)) as connection:
            yield connection

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get("/products/missing-product")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "Product not found" in response.json()["detail"]


def test_get_product_by_barcode_returns_product(tmp_path) -> None:
    db_path = tmp_path / "product_read_api.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        with get_connection(str(db_path)) as connection:
            yield connection

    with get_connection(str(db_path)) as connection:
        create_product(
            connection,
            ProductProfile(
                product_id="prod-002",
                barcode="9988776655443",
                product_name="Tomato Soup",
                brand="Kitchen Co",
                status="active",
            ),
        )

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get("/products/by-barcode/9988776655443")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["barcode"] == "9988776655443"
    assert payload["product_name"] == "Tomato Soup"


def test_get_product_by_barcode_returns_404_for_missing_barcode(tmp_path) -> None:
    db_path = tmp_path / "product_read_api.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        with get_connection(str(db_path)) as connection:
            yield connection

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get("/products/by-barcode/0000000000000")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "Product not found" in response.json()["detail"]
