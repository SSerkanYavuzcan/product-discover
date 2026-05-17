from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.main import app
from app.models import ProductProfile, SourceEvidence
from app.models.repository import add_product_evidence, create_product, list_products
from app.storage.database import get_connection, initialize_database


def _create_product(
    connection,
    *,
    product_id: str,
    product_name: str,
    status: str,
    barcode: str | None = None,
    created_at: datetime | None = None,
) -> ProductProfile:
    now = created_at or datetime.now(UTC)
    return create_product(
        connection,
        ProductProfile(
            product_id=product_id,
            barcode=barcode,
            product_name=product_name,
            status=status,
            description=None,
            images=[],
            created_at=now,
            updated_at=now,
        ),
    )


def test_get_products_returns_products(tmp_path) -> None:
    db_path = tmp_path / "product_list_api.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    with get_connection(str(db_path)) as connection:
        _create_product(
            connection,
            product_id="prod-001",
            barcode="1000000000001",
            product_name="Alpha",
            status="discovered",
        )
        _create_product(
            connection,
            product_id="prod-002",
            barcode="1000000000002",
            product_name="Beta",
            status="discovered",
        )

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get("/products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert len(payload["items"]) == 2
    assert payload["items"][0]["product_id"] is not None
    assert payload["items"][0]["product_name"] is not None


def test_get_products_supports_status_filter(tmp_path) -> None:
    db_path = tmp_path / "product_list_status.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    with get_connection(str(db_path)) as connection:
        _create_product(connection, product_id="prod-a", product_name="A", status="discovered")
        _create_product(connection, product_id="prod-b", product_name="B", status="draft")

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get("/products?status=discovered")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["product_id"] == "prod-a"


def test_get_products_supports_limit_and_offset(tmp_path) -> None:
    db_path = tmp_path / "product_list_pagination.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    base = datetime.now(UTC)
    with get_connection(str(db_path)) as connection:
        _create_product(
            connection,
            product_id="prod-1",
            product_name="A",
            status="discovered",
            created_at=base,
        )
        _create_product(
            connection,
            product_id="prod-2",
            product_name="B",
            status="discovered",
            created_at=base + timedelta(seconds=1),
        )
        _create_product(
            connection,
            product_id="prod-3",
            product_name="C",
            status="discovered",
            created_at=base + timedelta(seconds=2),
        )

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get("/products?limit=1&offset=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert len(payload["items"]) == 1


def test_get_products_returns_hydrated_description_and_images(tmp_path) -> None:
    db_path = tmp_path / "product_list_hydration.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    with get_connection(str(db_path)) as connection:
        created = _create_product(
            connection,
            product_id="prod-hydrated",
            product_name="Hydrated",
            status="discovered",
        )
        add_product_evidence(
            connection,
            created.product_id or "",
            SourceEvidence(
                source_name="Test",
                source_type="web",
                source_url="https://example.com/p",
                field_name="description",
                raw_value="Hydrated description",
                normalized_value="Hydrated description",
                confidence=0.9,
                extracted_at=datetime.now(UTC),
            ),
        )
        add_product_evidence(
            connection,
            created.product_id or "",
            SourceEvidence(
                source_name="Test",
                source_type="web",
                source_url="https://example.com/p",
                field_name="image",
                raw_value="https://example.com/image.jpg",
                normalized_value="https://example.com/image.jpg",
                confidence=0.95,
                extracted_at=datetime.now(UTC),
            ),
        )

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get("/products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["description"] == "Hydrated description"
    assert item["images"]
    assert item["images"][0]["url"] == "https://example.com/image.jpg"


def test_get_products_empty_list(tmp_path) -> None:
    db_path = tmp_path / "product_list_empty.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get("/products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 0
    assert payload["items"] == []


def test_products_route_ordering_hits_list_endpoint(tmp_path) -> None:
    db_path = tmp_path / "product_list_route_order.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection
    try:
        client = TestClient(app)
        response = client.get("/products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "count" in payload


def test_list_products_orders_by_created_at_desc_and_filters_status(tmp_path) -> None:
    db_path = tmp_path / "product_list_repo.db"
    initialize_database(str(db_path))

    base = datetime.now(UTC)
    with get_connection(str(db_path)) as connection:
        _create_product(
            connection,
            product_id="prod-older",
            product_name="Older",
            status="draft",
            created_at=base,
        )
        _create_product(
            connection,
            product_id="prod-newer",
            product_name="Newer",
            status="discovered",
            created_at=base + timedelta(seconds=2),
        )
        _create_product(
            connection,
            product_id="prod-middle",
            product_name="Middle",
            status="discovered",
            created_at=base + timedelta(seconds=1),
        )

        all_items = list_products(connection)
        discovered_items = list_products(connection, status="discovered")

    assert [item.product_id for item in all_items] == ["prod-newer", "prod-middle", "prod-older"]
    assert [item.product_id for item in discovered_items] == ["prod-newer", "prod-middle"]
