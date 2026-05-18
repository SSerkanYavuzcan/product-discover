import sqlite3
from urllib.parse import urlparse
from uuid import uuid4

from app.jobs.models import DiscoveryJob, JobPriority, JobStatus, JobType
from app.jobs.repository import create_discovery_job


def normalize_url(url: str) -> str:
    return url.strip()


def is_valid_url(url: str) -> bool:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def create_url_extraction_job(
    connection: sqlite3.Connection,
    url: str,
    priority: JobPriority = JobPriority.normal,
    batch_id: str | None = None,
    source_id: str | None = None,
) -> DiscoveryJob:
    normalized = normalize_url(url)
    if not is_valid_url(normalized):
        msg = "Invalid URL: must include http/https scheme and host"
        raise ValueError(msg)

    job = DiscoveryJob(
        job_id=str(uuid4()),
        job_type=JobType.url_extraction,
        status=JobStatus.pending,
        priority=priority,
        input_type="url",
        input_value=normalized,
        batch_id=batch_id,
        source_id=source_id,
    )
    return create_discovery_job(connection, job)
