from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    not_found = "not_found"
    needs_review = "needs_review"
    skipped_duplicate = "skipped_duplicate"
    rate_limited = "rate_limited"
    cancelled = "cancelled"


class JobType(StrEnum):
    barcode_lookup = "barcode_lookup"
    url_extraction = "url_extraction"
    product_name_search = "product_name_search"
    image_extraction = "image_extraction"
    batch_barcode_ingestion = "batch_barcode_ingestion"
    source_discovery = "source_discovery"
    sitemap_discovery = "sitemap_discovery"
    category_discovery = "category_discovery"
    refresh_product = "refresh_product"
    fill_missing_fields = "fill_missing_fields"


class JobPriority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class DiscoveryJob(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus = JobStatus.pending
    priority: JobPriority = JobPriority.normal
    input_type: str
    input_value: str
    batch_id: str | None = None
    product_id: str | None = None
    source_id: str | None = None
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    error_message: str | None = None
    result_product_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BatchJob(BaseModel):
    batch_id: str
    batch_type: JobType
    status: JobStatus = JobStatus.pending
    filename: str | None = None
    total_items: int = Field(default=0, ge=0)
    unique_items: int = Field(default=0, ge=0)
    pending_count: int = Field(default=0, ge=0)
    running_count: int = Field(default=0, ge=0)
    completed_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    not_found_count: int = Field(default=0, ge=0)
    needs_review_count: int = Field(default=0, ge=0)
    skipped_duplicate_count: int = Field(default=0, ge=0)
    rate_limited_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_unique_items(self) -> "BatchJob":
        if self.total_items > 0 and self.unique_items > self.total_items:
            msg = "unique_items must not be greater than total_items"
            raise ValueError(msg)
        return self


class BatchJobProgress(BaseModel):
    batch_id: str
    total_items: int = Field(ge=0)
    processed_items: int = Field(ge=0)
    progress_ratio: float = Field(ge=0, le=1)
    status: JobStatus

    @model_validator(mode="after")
    def validate_processed_items(self) -> "BatchJobProgress":
        if self.total_items > 0 and self.processed_items > self.total_items:
            msg = "processed_items must not be greater than total_items"
            raise ValueError(msg)
        return self
