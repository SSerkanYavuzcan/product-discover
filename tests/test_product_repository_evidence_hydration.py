import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.models import (
    ProductProfile,
    SourceEvidence,
    add_product_evidence,
    create_product,
    get_product,
    get_product_by_barcode,
)
from app.storage import get_connection, initialize_database


@pytest.fixture
def db_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "product_repository_hydration.db"
    initialize_database(str(db_path))
    connection = get_connection(str(db_path))
    try:
        yield connection
    finally:
        connection.close()


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _create_base_product(db_connection: sqlite3.Connection, *, barcode: str | None = None) -> str:
    product = create_product(
        db_connection,
        ProductProfile(product_name="Base Product", barcode=barcode, status="draft"),
    )
    return product.product_id or ""


def test_get_product_hydrates_description_from_evidence(db_connection: sqlite3.Connection) -> None:
    product_id = _create_base_product(db_connection)
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/product",
            field_name="description",
            raw_value="Great sparkling water",
            normalized_value=None,
            confidence=0.6,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )

    fetched = get_product(db_connection, product_id)

    assert fetched is not None
    assert fetched.description == "Great sparkling water"


def test_normalized_description_value_is_preferred(db_connection: sqlite3.Connection) -> None:
    product_id = _create_base_product(db_connection)
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/product",
            field_name="description",
            raw_value="raw desc",
            normalized_value="normalized desc",
            confidence=0.6,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )

    fetched = get_product(db_connection, product_id)

    assert fetched is not None
    assert fetched.description == "normalized desc"


def test_highest_confidence_description_wins(db_connection: sqlite3.Connection) -> None:
    product_id = _create_base_product(db_connection)
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/a",
            field_name="description",
            raw_value="lower",
            normalized_value=None,
            confidence=0.5,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/b",
            field_name="description",
            raw_value="higher",
            normalized_value=None,
            confidence=0.8,
            extracted_at=_dt("2026-01-02T00:00:00+00:00"),
        ),
    )

    fetched = get_product(db_connection, product_id)

    assert fetched is not None
    assert fetched.description == "higher"


def test_tied_confidence_uses_most_recent_description(db_connection: sqlite3.Connection) -> None:
    product_id = _create_base_product(db_connection)
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/a",
            field_name="description",
            raw_value="older",
            normalized_value=None,
            confidence=0.7,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/b",
            field_name="description",
            raw_value="newer",
            normalized_value=None,
            confidence=0.7,
            extracted_at=_dt("2026-01-03T00:00:00+00:00"),
        ),
    )

    fetched = get_product(db_connection, product_id)

    assert fetched is not None
    assert fetched.description == "newer"


def test_get_product_hydrates_images_from_evidence(db_connection: sqlite3.Connection) -> None:
    product_id = _create_base_product(db_connection)
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/product",
            field_name="image",
            raw_value=None,
            normalized_value="https://example.com/image.png",
            confidence=0.6,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )

    fetched = get_product(db_connection, product_id)

    assert fetched is not None
    assert len(fetched.images) == 1
    assert fetched.images[0].url == "https://example.com/image.png"
    assert fetched.images[0].image_type == "main"
    assert fetched.images[0].source_url == "https://example.com/product"
    assert fetched.images[0].confidence == 0.6


def test_image_url_field_is_supported(db_connection: sqlite3.Connection) -> None:
    product_id = _create_base_product(db_connection)
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/product",
            field_name="image_url",
            raw_value="https://example.com/image2.png",
            normalized_value=None,
            confidence=0.61,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )

    fetched = get_product(db_connection, product_id)

    assert fetched is not None
    assert len(fetched.images) == 1
    assert fetched.images[0].url == "https://example.com/image2.png"


def test_duplicate_image_urls_are_deduplicated(db_connection: sqlite3.Connection) -> None:
    product_id = _create_base_product(db_connection)
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/a",
            field_name="image",
            raw_value="https://example.com/image.png",
            normalized_value=None,
            confidence=0.5,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/b",
            field_name="image",
            raw_value="https://example.com/image.png",
            normalized_value=None,
            confidence=0.9,
            extracted_at=_dt("2026-01-02T00:00:00+00:00"),
        ),
    )

    fetched = get_product(db_connection, product_id)

    assert fetched is not None
    assert len(fetched.images) == 1
    assert fetched.images[0].source_url == "https://example.com/b"
    assert fetched.images[0].confidence == 0.9


def test_existing_direct_description_is_not_overwritten(db_connection: sqlite3.Connection) -> None:
    product_id = _create_base_product(db_connection)
    created = get_product(db_connection, product_id)
    assert created is not None

    updated = created.model_copy(update={"description": "direct description"})

    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/product",
            field_name="description",
            raw_value="evidence description",
            normalized_value=None,
            confidence=0.8,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )

    from app.models.repository import _hydrate_product_from_evidence

    fetched = get_product(db_connection, product_id)
    assert fetched is not None
    hydrated = _hydrate_product_from_evidence(updated, fetched.evidence)

    assert hydrated.description == "direct description"


def test_confidence_field_scores_are_hydrated_from_evidence(
    db_connection: sqlite3.Connection,
) -> None:
    product_id = _create_base_product(db_connection)
    db_connection.execute(
        "UPDATE products SET confidence_overall = ? WHERE product_id = ?",
        (0.5, product_id),
    )
    db_connection.commit()

    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/product",
            field_name="product_name",
            raw_value="Base Product",
            normalized_value=None,
            confidence=0.65,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/product",
            field_name="description",
            raw_value="Description",
            normalized_value=None,
            confidence=0.6,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/product",
            field_name="image",
            raw_value="https://example.com/image.png",
            normalized_value=None,
            confidence=0.55,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )

    fetched = get_product(db_connection, product_id)

    assert fetched is not None
    assert fetched.confidence is not None
    assert fetched.confidence.overall == 0.5
    assert fetched.confidence.field_scores["product_name"] == 0.65
    assert fetched.confidence.field_scores["description"] == 0.6
    assert fetched.confidence.field_scores["image"] == 0.55


def test_get_product_by_barcode_returns_hydrated_fields(db_connection: sqlite3.Connection) -> None:
    product_id = _create_base_product(db_connection, barcode="123456")
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/product",
            field_name="description",
            raw_value="Hydrated description",
            normalized_value=None,
            confidence=0.7,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )
    add_product_evidence(
        db_connection,
        product_id,
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            source_url="https://example.com/product",
            field_name="image",
            raw_value="https://example.com/barcode-image.png",
            normalized_value=None,
            confidence=0.7,
            extracted_at=_dt("2026-01-01T00:00:00+00:00"),
        ),
    )

    fetched = get_product_by_barcode(db_connection, "123456")

    assert fetched is not None
    assert fetched.description == "Hydrated description"
    assert len(fetched.images) == 1
    assert fetched.images[0].url == "https://example.com/barcode-image.png"
