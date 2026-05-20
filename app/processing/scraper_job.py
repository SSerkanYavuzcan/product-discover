import sqlite3
from datetime import UTC, datetime

from app.models import ConfidenceScore, ProductImage, ProductProfile, SourceEvidence
from app.models.repository import (
    add_product_evidence,
    normalize_source_url,
    upsert_product_profile,
)
from app.scrapers.base import ScrapedProduct
from app.sources.models import SourceRegistry


def persist_scraped_products(
    connection: sqlite3.Connection,
    source: SourceRegistry,
    scraped_products: list[ScrapedProduct],
) -> tuple[int, int, list[str]]:
    persisted = 0
    skipped = 0
    errors: list[str] = []
    now = datetime.now(UTC)

    for item in scraped_products:
        try:
            product = ProductProfile(
                product_name=item.product_name,
                barcode=item.barcode,
                brand=item.brand,
                category=item.category,
                images=[ProductImage(url=item.image_url)] if item.image_url else [],
                confidence=ConfidenceScore(overall=0.6, field_scores={"product_name": 0.9}),
                status="draft",
            )
            saved = upsert_product_profile(connection, product, source_url=item.source_url)

            evidence_items = [
                SourceEvidence(
                    source_id=source.source_id,
                    source_name=source.source_name,
                    source_type=source.source_type,
                    source_url=item.source_url,
                    field_name="product_name",
                    raw_value=item.product_name,
                    normalized_value=item.product_name,
                    confidence=0.9,
                    extracted_at=now,
                )
            ]
            if item.barcode:
                evidence_items.append(
                    SourceEvidence(
                        source_id=source.source_id,
                        source_name=source.source_name,
                        source_type=source.source_type,
                        source_url=item.source_url,
                        field_name="barcode",
                        raw_value=item.barcode,
                        normalized_value=item.barcode,
                        confidence=0.8,
                        extracted_at=now,
                    )
                )
            if item.image_url:
                evidence_items.append(
                    SourceEvidence(
                        source_id=source.source_id,
                        source_name=source.source_name,
                        source_type=source.source_type,
                        source_url=item.source_url,
                        field_name="image_url",
                        raw_value=item.image_url,
                        normalized_value=item.image_url,
                        confidence=0.7,
                        extracted_at=now,
                    )
                )
            evidence_items.append(
                SourceEvidence(
                    source_id=source.source_id,
                    source_name=source.source_name,
                    source_type=source.source_type,
                    source_url=item.source_url,
                    field_name="source_url",
                    raw_value=item.source_url,
                    normalized_value=normalize_source_url(item.source_url),
                    confidence=1.0,
                    extracted_at=now,
                )
            )

            for evidence in evidence_items:
                add_product_evidence(connection, saved.product_id or "", evidence)
            persisted += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    return persisted, skipped, errors
