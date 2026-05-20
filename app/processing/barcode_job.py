import sqlite3
from collections.abc import Callable

from app.extractors.open_food_facts import fetch_open_food_facts_product
from app.jobs.models import DiscoveryJob, JobStatus, JobType
from app.jobs.repository import (
    get_discovery_job,
    increment_discovery_job_attempt,
    update_discovery_job_status,
)
from app.models import ProductProfile
from app.models.repository import (
    add_product_evidence,
    upsert_product_profile,
)


def process_barcode_lookup_job(
    connection: sqlite3.Connection,
    job_id: str,
    fetcher: Callable[[str], ProductProfile | None] = fetch_open_food_facts_product,
) -> DiscoveryJob | None:
    job = get_discovery_job(connection, job_id)
    if job is None:
        return None

    if job.job_type != JobType.barcode_lookup:
        msg = f"Job {job_id} is not a barcode_lookup job"
        raise ValueError(msg)

    update_discovery_job_status(connection, job_id, JobStatus.running)
    increment_discovery_job_attempt(connection, job_id)

    try:
        product = fetcher(job.input_value)
        if product is None:
            return update_discovery_job_status(connection, job_id, JobStatus.not_found)

        saved = upsert_product_profile(connection, product)

        for evidence in product.evidence:
            add_product_evidence(connection, saved.product_id or "", evidence)

        return update_discovery_job_status(
            connection,
            job_id,
            JobStatus.completed,
            result_product_id=saved.product_id,
        )
    except Exception as exc:  # noqa: BLE001
        return update_discovery_job_status(
            connection,
            job_id,
            JobStatus.failed,
            error_message=f"Barcode lookup processing failed: {exc}",
        )
