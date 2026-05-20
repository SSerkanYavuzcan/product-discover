import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.models import (
    ConfidenceScore,
    ProductImage,
    ProductProfile,
    SourceEvidence,
    add_product_evidence,
    create_product,
    delete_product,
    get_product,
    get_product_by_barcode,
    list_product_evidence,
    update_product,
    upsert_product_profile,
)
from app.models.repository import evaluate_product_quality
from app.storage import get_connection, initialize_database


@pytest.fixture
def db_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "product_repository.db"
    initialize_database(str(db_path))
    connection = get_connection(str(db_path))
    try:
        yield connection
    finally:
        connection.close()


def test_create_product_inserts_product(db_connection: sqlite3.Connection) -> None:
    product = ProductProfile(product_id="p-1", product_name="Water", status="draft")

    created = create_product(db_connection, product)

    assert created.product_id == "p-1"
    assert created.product_name == "Water"


def test_create_product_generates_product_id_when_missing(
    db_connection: sqlite3.Connection,
) -> None:
    product = ProductProfile(product_name="Juice", status="draft")

    created = create_product(db_connection, product)

    assert created.product_id is not None


def test_get_product_returns_inserted_product(db_connection: sqlite3.Connection) -> None:
    created = create_product(
        db_connection,
        ProductProfile(product_id="p-2", product_name="Soda", barcode="111", status="draft"),
    )

    fetched = get_product(db_connection, created.product_id or "")

    assert fetched is not None
    assert fetched.product_id == "p-2"


def test_get_product_returns_none_for_missing(db_connection: sqlite3.Connection) -> None:
    assert get_product(db_connection, "missing") is None


def test_get_product_by_barcode_returns_correct_product(db_connection: sqlite3.Connection) -> None:
    create_product(
        db_connection,
        ProductProfile(product_id="p-3", barcode="12345", product_name="Tea", status="draft"),
    )

    fetched = get_product_by_barcode(db_connection, "12345")

    assert fetched is not None
    assert fetched.product_id == "p-3"


def test_get_product_by_barcode_missing_returns_none(db_connection: sqlite3.Connection) -> None:
    assert get_product_by_barcode(db_connection, "missing") is None


def test_duplicate_product_id_insertion_raises_integrity_error(
    db_connection: sqlite3.Connection,
) -> None:
    product = ProductProfile(product_id="dup-1", product_name="Milk", status="draft")
    create_product(db_connection, product)

    with pytest.raises(sqlite3.IntegrityError):
        create_product(db_connection, product)


def test_update_product_updates_fields_and_updated_at(db_connection: sqlite3.Connection) -> None:
    created = create_product(
        db_connection,
        ProductProfile(product_id="p-4", product_name="Chips", brand="BrandA", status="draft"),
    )
    original_updated_at = created.updated_at

    updated_model = created.model_copy(
        update={
            "product_name": "Potato Chips",
            "brand": "BrandB",
            "confidence": ConfidenceScore(overall=0.8),
        }
    )
    updated = update_product(db_connection, updated_model)

    assert updated is not None
    assert updated.product_name == "Potato Chips"
    assert updated.brand == "BrandB"
    assert updated.confidence is not None
    assert updated.confidence.overall == 0.8
    assert updated.updated_at >= original_updated_at


def test_update_product_returns_none_for_missing_product(db_connection: sqlite3.Connection) -> None:
    missing = ProductProfile(product_id="missing", product_name="X", status="draft")
    assert update_product(db_connection, missing) is None


def test_add_product_evidence_inserts_evidence(db_connection: sqlite3.Connection) -> None:
    created = create_product(
        db_connection,
        ProductProfile(product_id="p-5", product_name="Cereal", status="draft"),
    )
    evidence = SourceEvidence(
        source_name="catalog",
        source_type="url",
        field_name="product_name",
        raw_value="Cereal",
        normalized_value="Cereal",
        confidence=0.9,
        extracted_at=datetime.now(UTC),
    )

    inserted = add_product_evidence(db_connection, created.product_id or "", evidence)

    assert inserted.field_name == "product_name"


def test_list_product_evidence_returns_evidence(db_connection: sqlite3.Connection) -> None:
    created = create_product(
        db_connection,
        ProductProfile(product_id="p-6", product_name="Bread", status="draft"),
    )

    add_product_evidence(
        db_connection,
        created.product_id or "",
        SourceEvidence(
            source_name="dataset",
            source_type="file",
            field_name="brand",
            raw_value="BrandX",
            normalized_value="BrandX",
            confidence=0.8,
            extracted_at=datetime.now(UTC),
        ),
    )

    evidence_rows = list_product_evidence(db_connection, created.product_id or "")

    assert len(evidence_rows) == 1
    assert evidence_rows[0].field_name == "brand"


def test_list_product_evidence_empty_when_none(db_connection: sqlite3.Connection) -> None:
    created = create_product(
        db_connection,
        ProductProfile(product_id="p-7", product_name="Fruit", status="draft"),
    )

    evidence_rows = list_product_evidence(db_connection, created.product_id or "")

    assert evidence_rows == []


def test_get_product_includes_evidence(db_connection: sqlite3.Connection) -> None:
    created = create_product(
        db_connection,
        ProductProfile(product_id="p-8", product_name="Yogurt", status="draft"),
    )
    add_product_evidence(
        db_connection,
        created.product_id or "",
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            field_name="category",
            raw_value="Dairy",
            normalized_value="Dairy",
            confidence=0.85,
            extracted_at=datetime.now(UTC),
        ),
    )

    fetched = get_product(db_connection, created.product_id or "")

    assert fetched is not None
    assert len(fetched.evidence) == 1
    assert fetched.evidence[0].field_name == "category"


def test_delete_product_deletes_product_and_evidence(db_connection: sqlite3.Connection) -> None:
    created = create_product(
        db_connection,
        ProductProfile(product_id="p-9", product_name="Nuts", status="draft"),
    )
    add_product_evidence(
        db_connection,
        created.product_id or "",
        SourceEvidence(
            source_name="dataset",
            source_type="file",
            field_name="ingredients",
            raw_value="nuts",
            normalized_value="nuts",
            confidence=0.7,
            extracted_at=datetime.now(UTC),
        ),
    )

    deleted = delete_product(db_connection, created.product_id or "")

    assert deleted is True
    assert get_product(db_connection, created.product_id or "") is None
    assert list_product_evidence(db_connection, created.product_id or "") == []


def test_delete_product_returns_false_for_missing(db_connection: sqlite3.Connection) -> None:
    assert delete_product(db_connection, "missing") is False


def test_upsert_by_source_url_updates_existing_record(db_connection: sqlite3.Connection) -> None:
    first = upsert_product_profile(
        db_connection, ProductProfile(product_name="Milk", brand="A"), "https://example.com/p/1"
    )
    second = upsert_product_profile(
        db_connection, ProductProfile(product_name="Milk 2", brand="B"), "https://example.com/p/1"
    )
    assert first.product_id == second.product_id
    assert second.product_name == "Milk 2"


def test_upsert_by_barcode_updates_across_urls(db_connection: sqlite3.Connection) -> None:
    first = upsert_product_profile(
        db_connection, ProductProfile(product_name="Tea", barcode="123"), "https://a.com/p/tea"
    )
    second = upsert_product_profile(
        db_connection, ProductProfile(product_name="Tea New", barcode="123"), "https://b.com/p/tea"
    )
    assert first.product_id == second.product_id


def test_upsert_by_normalized_name_and_domain(db_connection: sqlite3.Connection) -> None:
    first = upsert_product_profile(
        db_connection, ProductProfile(product_name="Ultra  Cleaner!!"), "https://shop.com/p/1"
    )
    second = upsert_product_profile(
        db_connection, ProductProfile(product_name=" ultra cleaner "), "https://shop.com/p/2"
    )
    assert first.product_id == second.product_id


def test_upsert_does_not_override_good_values_with_empty(db_connection: sqlite3.Connection) -> None:
    first = upsert_product_profile(
        db_connection, ProductProfile(product_name="Soap", brand="Brand A"), "https://shop.com/p/1"
    )
    second = upsert_product_profile(
        db_connection, ProductProfile(product_name="Soap", brand=""), "https://shop.com/p/1"
    )
    assert second.product_id == first.product_id
    assert second.brand == "Brand A"


def test_quality_score_prefers_more_complete_profile() -> None:
    rich = ProductProfile(product_name="P", brand="B", images=[ProductImage(url="https://x/img.jpg")])
    rich_score, rich_flags = evaluate_product_quality(rich, "https://x/p")
    poor_score, poor_flags = evaluate_product_quality(ProductProfile(product_name="P"), None)
    assert rich_score > poor_score
    assert "missing_brand" not in rich_flags
    assert "missing_source_url" in poor_flags
