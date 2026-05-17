import json
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.request import urlopen

from app.models import ConfidenceScore, NutritionFacts, ProductImage, ProductProfile, SourceEvidence


def build_open_food_facts_url(barcode: str) -> str:
    return f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_open_food_facts_product(payload: dict, barcode: str) -> ProductProfile | None:
    if payload.get("status") != 1:
        return None

    product = payload.get("product")
    if not isinstance(product, dict):
        return None

    source_url = build_open_food_facts_url(barcode)
    extracted_at = datetime.now(UTC)

    product_name = (
        product.get("product_name")
        or product.get("product_name_en")
        or product.get("generic_name")
    )
    brand = product.get("brands")
    category = product.get("categories")
    description = product.get("generic_name") or product_name

    image_url = product.get("image_front_url") or product.get("image_url")
    images = [
        ProductImage(url=image_url, image_type="front", source_url=source_url, confidence=0.9)
    ] if image_url else []

    nutriments = product.get("nutriments") if isinstance(product.get("nutriments"), dict) else {}
    nutrition = None
    if nutriments:
        nutrition = NutritionFacts(
            energy_kcal=_as_float(
                nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal")
            ),
            fat_g=_as_float(nutriments.get("fat_100g")),
            saturated_fat_g=_as_float(nutriments.get("saturated-fat_100g")),
            carbohydrates_g=_as_float(nutriments.get("carbohydrates_100g")),
            sugars_g=_as_float(nutriments.get("sugars_100g")),
            protein_g=_as_float(nutriments.get("proteins_100g")),
            salt_g=_as_float(nutriments.get("salt_100g")),
            fiber_g=_as_float(nutriments.get("fiber_100g")),
        )

    ingredients_text = product.get("ingredients_text")
    ingredients = (
        [ingredients_text]
        if isinstance(ingredients_text, str) and ingredients_text
        else []
    )

    allergens_tags = product.get("allergens_tags")
    if isinstance(allergens_tags, list):
        allergens = [str(tag) for tag in allergens_tags if str(tag)]
    else:
        allergen_value = product.get("allergens")
        allergens = [allergen_value] if isinstance(allergen_value, str) and allergen_value else []

    evidence: list[SourceEvidence] = []

    def add_evidence(
        field_name: str,
        raw_value: object,
        normalized_value: object,
        confidence: float,
    ) -> None:
        evidence.append(
            SourceEvidence(
                source_name="Open Food Facts",
                source_type="open_database",
                source_url=source_url,
                field_name=field_name,
                raw_value=str(raw_value) if raw_value is not None else None,
                normalized_value=str(normalized_value) if normalized_value is not None else None,
                confidence=confidence,
                extracted_at=extracted_at,
            )
        )

    field_scores: dict[str, float] = {}

    if product_name:
        add_evidence("product_name", product.get("product_name"), product_name, 0.9)
        field_scores["product_name"] = 0.9
    if brand:
        add_evidence("brand", brand, brand, 0.8)
        field_scores["brand"] = 0.8
    if category:
        add_evidence("category", category, category, 0.7)
        field_scores["category"] = 0.7
    if image_url:
        add_evidence("image", image_url, image_url, 0.8)
        field_scores["image"] = 0.8
    if ingredients:
        add_evidence("ingredients", ingredients_text, ingredients_text, 0.7)
        field_scores["ingredients"] = 0.7

    for field_name, nutriment_key in {
        "energy_kcal": "energy-kcal_100g",
        "fat_g": "fat_100g",
        "saturated_fat_g": "saturated-fat_100g",
        "carbohydrates_g": "carbohydrates_100g",
        "sugars_g": "sugars_100g",
        "protein_g": "proteins_100g",
        "salt_g": "salt_100g",
        "fiber_g": "fiber_100g",
    }.items():
        if nutriments.get(nutriment_key) is not None:
            parsed_value = _as_float(nutriments.get(nutriment_key))
            if parsed_value is not None:
                add_evidence(field_name, nutriments.get(nutriment_key), parsed_value, 0.75)
                field_scores[field_name] = 0.75

    overall = round(sum(field_scores.values()) / len(field_scores), 3) if field_scores else 0.0

    return ProductProfile(
        barcode=barcode,
        gtin=barcode,
        product_name=product_name,
        brand=brand,
        category=category,
        description=description,
        images=images,
        nutrition=nutrition,
        ingredients=ingredients,
        allergens=allergens,
        evidence=evidence,
        confidence=ConfidenceScore(overall=overall, field_scores=field_scores),
        status="discovered",
    )


def fetch_open_food_facts_product(
    barcode: str, timeout_seconds: float = 10.0
) -> ProductProfile | None:
    url = build_open_food_facts_url(barcode)
    try:
        with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    return parse_open_food_facts_product(payload, barcode)
