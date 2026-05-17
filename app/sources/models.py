from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SourceRegistry(BaseModel):
    source_id: str | None = None
    source_name: str
    source_type: str
    base_url: str
    country: str | None = None
    language: str | None = None
    is_active: bool = True
    priority: int = Field(default=100, ge=0)
    crawl_frequency_hours: int | None = Field(default=None, ge=1)
    robots_policy: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class DiscoveredUrl(BaseModel):
    url_id: str | None = None
    source_id: str | None = None
    url: str
    url_hash: str | None = None
    discovery_type: str
    status: str
    barcode: str | None = None
    product_id: str | None = None
    first_seen_at: datetime = Field(default_factory=_utc_now)
    last_seen_at: datetime = Field(default_factory=_utc_now)
    last_checked_at: datetime | None = None
    error_message: str | None = None


class ExtractionRun(BaseModel):
    run_id: str | None = None
    source_id: str | None = None
    status: str
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    pages_seen: int = Field(default=0, ge=0)
    products_found: int = Field(default=0, ge=0)
    error_message: str | None = None
