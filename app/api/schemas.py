from datetime import datetime

from pydantic import BaseModel

from app.jobs.models import JobPriority, JobStatus, JobType


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
