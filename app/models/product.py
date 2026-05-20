from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.evidence import ConfidenceScore, ProductImage, SourceEvidence
from app.models.nutrition import NutritionFacts


class PackageInfo(BaseModel):
    size: float | None = None
    unit: str | None = None
    pack_count: int | None = 1
    raw_text: str | None = None


class ProductProfile(BaseModel):
    product_id: str | None = None
    barcode: str | None = None
    gtin: str | None = None
    product_name: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    category: str | None = None
    description: str | None = None
    package: PackageInfo | None = None
    images: list[ProductImage] = Field(default_factory=list)
    nutrition: NutritionFacts | None = None
    ingredients: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    evidence: list[SourceEvidence] = Field(default_factory=list)
    confidence: ConfidenceScore | None = None
    quality_score: float | None = None
    quality_flags: list[str] = Field(default_factory=list)
    status: str = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
