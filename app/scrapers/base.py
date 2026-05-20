from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.sources.models import SourceRegistry


class ScrapedProduct(BaseModel):
    product_name: str
    source_url: str
    image_url: str | None = None
    brand: str | None = None
    category: str | None = None
    barcode: str | None = None
    price: float | None = None
    currency: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)


class BaseSiteScraper(ABC):
    domain_patterns: list[str] = []

    def can_handle(self, source_url: str) -> bool:
        hostname = (urlparse(source_url).hostname or "").lower()
        return any(
            hostname == pattern or hostname.endswith(f".{pattern}")
            for pattern in self.domain_patterns
        )

    @abstractmethod
    def scrape(self, source: SourceRegistry, limit: int = 100) -> list[ScrapedProduct]:
        raise NotImplementedError
