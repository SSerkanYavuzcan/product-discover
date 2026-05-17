import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from app.models.evidence import ConfidenceScore, ProductImage, SourceEvidence
from app.models.product import ProductProfile


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _serialize_product(product: ProductProfile) -> dict[str, object | None]:
    confidence_overall = product.confidence.overall if product.confidence is not None else None
    return {
        "product_id": product.product_id,
        "barcode": product.barcode,
        "gtin": product.gtin,
        "product_name": product.product_name,
        "brand": product.brand,
        "category": product.category,
        "status": product.status,
        "confidence_overall": confidence_overall,
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }


def _deserialize_evidence(row: sqlite3.Row) -> SourceEvidence:
    return SourceEvidence(
        source_name=row["source_name"],
        source_type=row["source_type"],
        source_url=row["source_url"],
        field_name=row["field_name"],
        raw_value=row["raw_value"],
        normalized_value=row["normalized_value"],
        confidence=row["confidence"],
        extracted_at=datetime.fromisoformat(row["extracted_at"]),
    )


def _hydrate_product_from_evidence(
    product: ProductProfile, evidence: list[SourceEvidence]
) -> ProductProfile:
    hydrated = product.model_copy(deep=True)
    if not evidence:
        return hydrated

    field_max_confidence: dict[str, float] = {}
    for item in evidence:
        previous = field_max_confidence.get(item.field_name)
        if previous is None or item.confidence > previous:
            field_max_confidence[item.field_name] = item.confidence

    if hydrated.description is None:
        description_evidence = [item for item in evidence if item.field_name == "description"]
        if description_evidence:
            winner = max(
                description_evidence, key=lambda item: (item.confidence, item.extracted_at)
            )
            value = (
                winner.normalized_value
                if winner.normalized_value is not None
                else winner.raw_value
            )
            if value is not None:
                hydrated.description = str(value)

    if not hydrated.images:
        image_evidence = [item for item in evidence if item.field_name in {"image", "image_url"}]
        sorted_image_evidence = sorted(
            image_evidence,
            key=lambda item: (item.confidence, item.extracted_at),
            reverse=True,
        )
        seen_urls: set[str] = set()
        hydrated_images: list[ProductImage] = []
        for item in sorted_image_evidence:
            value = item.normalized_value if item.normalized_value is not None else item.raw_value
            if value is None:
                continue
            image_url = str(value).strip()
            if not image_url or image_url in seen_urls:
                continue
            seen_urls.add(image_url)
            hydrated_images.append(
                ProductImage(
                    url=image_url,
                    image_type="main" if not hydrated_images else "gallery",
                    source_url=item.source_url,
                    confidence=item.confidence,
                )
            )
        hydrated.images = hydrated_images

    if hydrated.confidence is not None:
        merged_scores = dict(hydrated.confidence.field_scores)
        for field_name, score in field_max_confidence.items():
            if field_name not in merged_scores:
                merged_scores[field_name] = score
        hydrated.confidence = ConfidenceScore(
            overall=hydrated.confidence.overall,
            field_scores=merged_scores,
        )
    else:
        overall = round(sum(item.confidence for item in evidence) / len(evidence), 3)
        hydrated.confidence = ConfidenceScore(overall=overall, field_scores=field_max_confidence)

    return hydrated


def _deserialize_product(row: sqlite3.Row, evidence: list[SourceEvidence]) -> ProductProfile:
    confidence_value = row["confidence_overall"]
    confidence = ConfidenceScore(overall=confidence_value) if confidence_value is not None else None
    product = ProductProfile(
        product_id=row["product_id"],
        barcode=row["barcode"],
        gtin=row["gtin"],
        product_name=row["product_name"],
        brand=row["brand"],
        category=row["category"],
        status=row["status"],
        confidence=confidence,
        evidence=evidence,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
    return _hydrate_product_from_evidence(product, evidence)


def create_product(connection: sqlite3.Connection, product: ProductProfile) -> ProductProfile:
    product_id = product.product_id or str(uuid4())
    stored_product = product.model_copy(update={"product_id": product_id})
    payload = _serialize_product(stored_product)
    connection.execute(
        """
        INSERT INTO products (
            product_id, barcode, gtin, product_name, brand, category,
            status, confidence_overall, created_at, updated_at
        ) VALUES (
            :product_id, :barcode, :gtin, :product_name, :brand, :category,
            :status, :confidence_overall, :created_at, :updated_at
        )
        """,
        payload,
    )
    connection.commit()
    return get_product(connection, product_id) or stored_product


def get_product(connection: sqlite3.Connection, product_id: str) -> ProductProfile | None:
    row = connection.execute(
        "SELECT * FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()
    if row is None:
        return None
    evidence = list_product_evidence(connection, product_id)
    return _deserialize_product(row, evidence)


def get_product_by_barcode(connection: sqlite3.Connection, barcode: str) -> ProductProfile | None:
    row = connection.execute(
        "SELECT * FROM products WHERE barcode = ? ORDER BY created_at ASC LIMIT 1", (barcode,)
    ).fetchone()
    if row is None:
        return None
    product_id = row["product_id"]
    evidence = list_product_evidence(connection, product_id)
    return _deserialize_product(row, evidence)


def update_product(
    connection: sqlite3.Connection,
    product: ProductProfile,
) -> ProductProfile | None:
    if product.product_id is None:
        return None

    existing = get_product(connection, product.product_id)
    if existing is None:
        return None

    now = _utc_now()
    updated_product = product.model_copy(update={"updated_at": now})
    payload = _serialize_product(updated_product)
    connection.execute(
        """
        UPDATE products
        SET barcode = :barcode,
            gtin = :gtin,
            product_name = :product_name,
            brand = :brand,
            category = :category,
            status = :status,
            confidence_overall = :confidence_overall,
            updated_at = :updated_at
        WHERE product_id = :product_id
        """,
        payload,
    )
    connection.commit()
    return get_product(connection, product.product_id)


def add_product_evidence(
    connection: sqlite3.Connection,
    product_id: str,
    evidence: SourceEvidence,
) -> SourceEvidence:
    connection.execute(
        """
        INSERT INTO product_evidence (
            evidence_id, product_id, source_name, source_type, source_url,
            field_name, raw_value, normalized_value, confidence, extracted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            product_id,
            evidence.source_name,
            evidence.source_type,
            evidence.source_url,
            evidence.field_name,
            None if evidence.raw_value is None else str(evidence.raw_value),
            None if evidence.normalized_value is None else str(evidence.normalized_value),
            evidence.confidence,
            evidence.extracted_at.isoformat(),
        ),
    )
    connection.commit()
    return evidence


def list_product_evidence(
    connection: sqlite3.Connection,
    product_id: str,
) -> list[SourceEvidence]:
    rows = connection.execute(
        "SELECT * FROM product_evidence WHERE product_id = ? ORDER BY extracted_at ASC",
        (product_id,),
    ).fetchall()
    return [_deserialize_evidence(row) for row in rows]


def delete_product(connection: sqlite3.Connection, product_id: str) -> bool:
    connection.execute("DELETE FROM product_evidence WHERE product_id = ?", (product_id,))
    result = connection.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
    connection.commit()
    return result.rowcount > 0
