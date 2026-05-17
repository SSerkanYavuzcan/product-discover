import sqlite3

from app.jobs.models import DiscoveryJob, JobType
from app.jobs.repository import get_discovery_job
from app.processing.barcode_job import process_barcode_lookup_job

try:
    from app.processing.url_job import process_url_extraction_job
except ModuleNotFoundError:  # pragma: no cover
    def process_url_extraction_job(
        connection: sqlite3.Connection,
        job_id: str,
    ) -> DiscoveryJob | None:
        msg = "URL extraction processor is unavailable"
        raise ValueError(msg)


def process_discovery_job(
    connection: sqlite3.Connection,
    job_id: str,
) -> DiscoveryJob | None:
    job = get_discovery_job(connection, job_id)
    if job is None:
        return None

    if job.job_type == JobType.barcode_lookup:
        return process_barcode_lookup_job(connection, job_id)

    if job.job_type == JobType.url_extraction:
        return process_url_extraction_job(connection, job_id)

    msg = f"Unsupported discovery job type: {job.job_type}"
    raise ValueError(msg)
