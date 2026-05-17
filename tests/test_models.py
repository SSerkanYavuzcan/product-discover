from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import (
    ConfidenceScore,
    NutritionFacts,
    PackageInfo,
    ProductImage,
    ProductProfile,
    SourceEvidence,
)


def test_product_profile_minimal_creation() -> None:
    product = ProductProfile()

    assert product.status == "draft"
    assert product.images == []
    assert product.ingredients == []
    assert product.allergens == []
    assert product.evidence == []


def test_product_profile_full_structure() -> None:
    product = ProductProfile(
        product_name="Sparkling Water",
        package=PackageInfo(size=500, unit="ml", pack_count=6, raw_text="6 x 500 ml"),
        images=[ProductImage(url="https://example.com/image.jpg", confidence=0.95)],
        nutrition=NutritionFacts(energy_kcal=0),
        evidence=[
            SourceEvidence(
                source_name="catalog",
                source_type="url",
                source_url="https://example.com/product",
                field_name="product_name",
                raw_value="Sparkling Water",
                normalized_value="Sparkling Water",
                confidence=0.92,
                extracted_at=datetime.now(UTC),
            )
        ],
        confidence=ConfidenceScore(overall=0.9, field_scores={"product_name": 0.95}),
    )

    assert product.package is not None
    assert product.nutrition is not None
    assert product.images[0].image_type == "main"
    assert product.evidence[0].field_name == "product_name"
    assert product.confidence is not None


def test_confidence_validation_errors() -> None:
    with pytest.raises(ValidationError):
        ProductImage(url="https://example.com/image.jpg", confidence=1.1)

    with pytest.raises(ValidationError):
        SourceEvidence(
            source_name="catalog",
            source_type="url",
            field_name="brand",
            raw_value="Brand",
            confidence=-0.1,
            extracted_at=datetime.now(UTC),
        )

    with pytest.raises(ValidationError):
        ConfidenceScore(overall=0.6, field_scores={"brand": 1.2})


def test_mutable_defaults_not_shared() -> None:
    one = ProductProfile()
    two = ProductProfile()

    one.ingredients.append("water")
    one.images.append(ProductImage(url="https://example.com/a.jpg"))
    one.evidence.append(
        SourceEvidence(
            source_name="dataset",
            source_type="file",
            field_name="ingredients",
            raw_value="water",
            confidence=0.8,
            extracted_at=datetime.now(UTC),
        )
    )

    assert two.ingredients == []
    assert two.images == []
    assert two.evidence == []


def test_timestamps_auto_populated() -> None:
    product = ProductProfile()

    assert isinstance(product.created_at, datetime)
    assert isinstance(product.updated_at, datetime)
    assert product.created_at.tzinfo is not None
    assert product.updated_at.tzinfo is not None
