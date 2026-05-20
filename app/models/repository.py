import re
import sqlite3
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import uuid4

from app.models.evidence import ConfidenceScore, ProductImage, SourceEvidence
from app.models.product import ProductProfile


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split()).strip()


def normalize_product_name(value: str | None) -> str | None:
    if not value:
        return None
    lowered = _normalize_whitespace(value).lower()
    cleaned = re.sub(r"[^\w\s-]", " ", lowered)
    normalized = _normalize_whitespace(cleaned)
    return normalized or None


def normalize_source_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if not host:
        return None
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    normalized = f"{scheme}://{host}{path}"
    return normalized.rstrip("/")


def _source_domain(value: str | None) -> str | None:
    normalized = normalize_source_url(value)
    if not normalized:
        return None
    return urlparse(normalized).netloc.lower() or None


def build_product_identity_key(
    product: ProductProfile, source_url: str | None = None
) -> str | None:
    barcode_or_gtin = (product.barcode or product.gtin or "").strip()
    if barcode_or_gtin:
        return f"barcode:{barcode_or_gtin}"
    normalized_source = normalize_source_url(source_url)
    if normalized_source:
        return f"source_url:{normalized_source}"
    normalized_name = normalize_product_name(product.product_name)
    normalized_domain = _source_domain(source_url)
    if normalized_name and normalized_domain:
        return f"name_domain:{normalized_domain}:{normalized_name}"
    return None


def evaluate_product_quality(
    product: ProductProfile, source_url: str | None = None
) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 0.0
    if product.product_name:
        score += 0.30
    if source_url:
        score += 0.15
    else:
        flags.append("missing_source_url")
    if product.images:
        score += 0.20
    else:
        flags.append("missing_image")
    if product.brand:
        score += 0.10
    else:
        flags.append("missing_brand")
    if product.barcode or product.gtin:
        score += 0.15
    else:
        flags.append("missing_barcode")
    if product.confidence is not None:
        score += 0.10
    else:
        flags.append("missing_price")
    return min(1.0, round(score, 2)), flags


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

    source_url = next((item.source_url for item in evidence if item.source_url), None)
    quality_score, quality_flags = evaluate_product_quality(hydrated, source_url=source_url)
    hydrated.quality_score = quality_score
    hydrated.quality_flags = quality_flags
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


def list_products(
    connection: sqlite3.Connection,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ProductProfile]:
    normalized_limit = 100 if limit <= 0 else min(limit, 500)
    normalized_offset = max(offset, 0)

    query = "SELECT * FROM products"
    params: list[object] = []
    if status is not None:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC, product_name ASC LIMIT ? OFFSET ?"
    params.extend([normalized_limit, normalized_offset])

    rows = connection.execute(query, tuple(params)).fetchall()
    products: list[ProductProfile] = []
    for row in rows:
        product_id = row["product_id"]
        evidence = list_product_evidence(connection, product_id)
        products.append(_deserialize_product(row, evidence))
    return products


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


def _choose_value(existing: str | None, new: str | None) -> str | None:
    if new is None or not str(new).strip():
        return existing
    return new


def upsert_product_profile(
    connection: sqlite3.Connection, product_profile: ProductProfile, source_url: str | None = None
) -> ProductProfile:
    candidate = None
    barcode_or_gtin = (product_profile.barcode or product_profile.gtin or "").strip()
    if barcode_or_gtin:
        candidate = get_product_by_barcode(connection, barcode_or_gtin)
        if candidate is None and product_profile.gtin:
            row = connection.execute(
                "SELECT product_id FROM products WHERE gtin = ? ORDER BY created_at ASC LIMIT 1",
                (product_profile.gtin,),
            ).fetchone()
            candidate = get_product(connection, row["product_id"]) if row else None
    if candidate is None and source_url:
        normalized_source = normalize_source_url(source_url)
        if normalized_source:
            row = connection.execute(
                """
                SELECT product_id FROM product_evidence
                WHERE field_name = 'source_url' AND normalized_value = ?
                ORDER BY extracted_at DESC LIMIT 1
                """,
                (normalized_source,),
            ).fetchone()
            candidate = get_product(connection, row["product_id"]) if row else None
    if candidate is None and source_url and product_profile.product_name:
        normalized_name = normalize_product_name(product_profile.product_name)
        normalized_domain = _source_domain(source_url)
        if normalized_name and normalized_domain:
            rows = connection.execute("SELECT product_id, product_name FROM products").fetchall()
            for row in rows:
                existing = get_product(connection, row["product_id"])
                if existing is None:
                    continue
                existing_name = normalize_product_name(existing.product_name)
                existing_domain = _source_domain(
                    next((item.source_url for item in existing.evidence if item.source_url), None)
                )
                if existing_name == normalized_name and existing_domain == normalized_domain:
                    candidate = existing
                    break
    if candidate is None:
        saved = create_product(connection, product_profile)
    else:
        merged = candidate.model_copy(
            update={
                "barcode": _choose_value(candidate.barcode, product_profile.barcode),
                "gtin": _choose_value(candidate.gtin, product_profile.gtin),
                "product_name": _choose_value(candidate.product_name, product_profile.product_name),
                "brand": _choose_value(candidate.brand, product_profile.brand),
                "category": _choose_value(candidate.category, product_profile.category),
                "status": (
                    _choose_value(candidate.status, product_profile.status)
                    or candidate.status
                ),
                "confidence": product_profile.confidence or candidate.confidence,
                "images": product_profile.images or candidate.images,
                "created_at": candidate.created_at,
                "updated_at": _utc_now(),
            }
        )
        saved = update_product(connection, merged) or candidate

    if source_url and saved.product_id:
        add_product_evidence(
            connection,
            saved.product_id,
            SourceEvidence(
                source_name="product_discover",
                source_type="extraction",
                source_url=source_url,
                field_name="source_url",
                raw_value=source_url,
                normalized_value=normalize_source_url(source_url),
                confidence=1.0,
                extracted_at=_utc_now(),
            ),
        )
    return get_product(connection, saved.product_id or "") or saved


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
