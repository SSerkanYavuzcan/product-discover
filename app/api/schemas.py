from datetime import datetime

from pydantic import BaseModel, Field

from app.jobs.models import JobPriority, JobStatus, JobType
from app.models import (
    ConfidenceScore,
    NutritionFacts,
    PackageInfo,
    ProductImage,
    SourceEvidence,
)


class BarcodeIngestionRequest(BaseModel):
    barcode: str
    priority: JobPriority = JobPriority.normal
    batch_id: str | None = None


class BarcodeIngestionResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    priority: JobPriority
    input_type: str
    input_value: str
    batch_id: str | None = None
    created_at: datetime
    updated_at: datetime


class UrlIngestionRequest(BaseModel):
    url: str
    priority: JobPriority = JobPriority.normal
    batch_id: str | None = None


class UrlIngestionResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    priority: JobPriority
    input_type: str
    input_value: str
    batch_id: str | None = None
    created_at: datetime
    updated_at: datetime


class JobProcessResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    priority: JobPriority
    input_type: str
    input_value: str
    batch_id: str | None = None
    product_id: str | None = None
    source_id: str | None = None
    attempt_count: int
    max_attempts: int
    error_message: str | None = None
    result_product_id: str | None = None
    created_at: datetime
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class ProductReadResponse(BaseModel):
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
    status: str
    created_at: datetime
    updated_at: datetime


class SourceRegistryCreateRequest(BaseModel):
    source_name: str
    source_type: str
    base_url: str
    country: str | None = None
    language: str | None = None
    is_active: bool = True
    priority: int = 100
    crawl_frequency_hours: int | None = None
    robots_policy: str | None = None
    notes: str | None = None


class SourceRegistryResponse(BaseModel):
    source_id: str
    source_name: str
    source_type: str
    base_url: str
    country: str | None = None
    language: str | None = None
    is_active: bool
    priority: int
    crawl_frequency_hours: int | None = None
    robots_policy: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceActiveStatusRequest(BaseModel):
    is_active: bool


class SitemapDiscoveryRequest(BaseModel):
    max_child_sitemaps: int = Field(default=5, ge=0)
    product_only: bool = True


class ExtractionRunResponse(BaseModel):
    run_id: str
    source_id: str | None = None
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    pages_seen: int
    products_found: int
    error_message: str | None = None


class DiscoveredUrlResponse(BaseModel):
    url_id: str
    source_id: str | None = None
    url: str
    url_hash: str
    discovery_type: str
    status: str
    barcode: str | None = None
    product_id: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    last_checked_at: datetime | None = None
    error_message: str | None = None


class DiscoveredUrlJobCreationRequest(BaseModel):
    status: str = "discovered"
    limit: int = Field(default=50, ge=1, le=500)
    priority: JobPriority = JobPriority.normal
    batch_id: str | None = None


class DiscoveredUrlJobCreationResponse(BaseModel):
    source_id: str
    status_filter: str
    requested_limit: int
    created_count: int
    skipped_count: int
    job_ids: list[str] = Field(default_factory=list)


class ProcessManyJobsRequest(BaseModel):
    job_ids: list[str] = Field(min_length=1)
    max_jobs: int = Field(default=10, ge=1, le=20)


class ProcessedJobItemResponse(BaseModel):
    job_id: str
    status: str
    job_type: JobType | None = None
    result_product_id: str | None = None
    error_message: str | None = None


class ProcessManyJobsResponse(BaseModel):
    requested_count: int
    processed_count: int
    skipped_count: int
    results: list[ProcessedJobItemResponse] = Field(default_factory=list)
