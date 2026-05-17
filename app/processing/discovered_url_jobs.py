import sqlite3
from dataclasses import dataclass

from app.ingestion.url import create_url_extraction_job
from app.jobs.models import JobPriority
from app.sources import get_source, list_discovered_urls_by_source, update_discovered_url_status


@dataclass
class DiscoveredUrlJobCreationResult:
    source_id: str
    status_filter: str
    requested_limit: int
    created_count: int
    skipped_count: int
    job_ids: list[str]


def create_url_extraction_jobs_from_discovered_urls(
    connection: sqlite3.Connection,
    source_id: str,
    status: str = "discovered",
    limit: int = 50,
    priority: JobPriority = JobPriority.normal,
    batch_id: str | None = None,
) -> DiscoveredUrlJobCreationResult | None:
    source = get_source(connection, source_id)
    if source is None:
        return None

    if limit <= 0:
        limit = 50
    if limit > 500:
        limit = 500

    discovered_urls = list_discovered_urls_by_source(
        connection=connection,
        source_id=source_id,
        status=status,
        limit=limit,
        offset=0,
    )

    job_ids: list[str] = []
    skipped_count = 0
    for discovered_url in discovered_urls:
        try:
            job = create_url_extraction_job(
                connection=connection,
                url=discovered_url.url,
                priority=priority,
                batch_id=batch_id,
            )
        except ValueError:
            skipped_count += 1
            continue

        job_ids.append(job.job_id)
        if discovered_url.url_id is not None:
            update_discovered_url_status(
                connection=connection,
                url_id=discovered_url.url_id,
                status="queued",
            )

    return DiscoveredUrlJobCreationResult(
        source_id=source_id,
        status_filter=status,
        requested_limit=limit,
        created_count=len(job_ids),
        skipped_count=skipped_count,
        job_ids=job_ids,
    )
