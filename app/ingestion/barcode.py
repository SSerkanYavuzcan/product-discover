import sqlite3
from uuid import uuid4

from app.jobs.models import DiscoveryJob, JobPriority, JobStatus, JobType
from app.jobs.repository import create_discovery_job

VALID_GTIN_LENGTHS = {8, 12, 13, 14}


def normalize_barcode(barcode: str) -> str:
    return barcode.strip().replace(" ", "").replace("-", "")


def is_valid_barcode(barcode: str) -> bool:
    normalized = normalize_barcode(barcode)
    if not normalized.isdigit():
        return False
    return len(normalized) in VALID_GTIN_LENGTHS


def create_barcode_lookup_job(
    connection: sqlite3.Connection,
    barcode: str,
    priority: JobPriority = JobPriority.normal,
    batch_id: str | None = None,
) -> DiscoveryJob:
    normalized = normalize_barcode(barcode)
    if not is_valid_barcode(normalized):
        raise ValueError("Invalid barcode: must be numeric GTIN with length 8, 12, 13, or 14")

    job = DiscoveryJob(
        job_id=str(uuid4()),
        job_type=JobType.barcode_lookup,
        status=JobStatus.pending,
        priority=priority,
        input_type="barcode",
        input_value=normalized,
        batch_id=batch_id,
    )
    return create_discovery_job(connection, job)
