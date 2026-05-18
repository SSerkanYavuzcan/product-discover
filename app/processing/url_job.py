import sqlite3
from collections.abc import Callable

try:
    from app.extractors.product_page import extract_product_from_url
except ModuleNotFoundError:  # pragma: no cover

    def extract_product_from_url(url: str):
        msg = "extract_product_from_url is unavailable"
        raise RuntimeError(msg)


from app.jobs.models import DiscoveryJob, JobStatus, JobType
from app.jobs.repository import (
    get_discovery_job,
    increment_discovery_job_attempt,
    update_discovery_job_status,
)
from app.models import ProductProfile
from app.models.repository import (
    add_product_evidence,
    create_product,
    get_product_by_barcode,
    update_product,
)
from app.sources import update_discovered_url_by_source_and_url


def _update_discovered_url_after_processing(
    connection: sqlite3.Connection,
    job: DiscoveryJob,
    status: str,
    error_message: str | None = None,
    product_id: str | None = None,
    barcode: str | None = None,
) -> None:
    try:
        update_discovered_url_by_source_and_url(
            connection=connection,
            source_id=job.source_id,
            url=job.input_value,
            status=status,
            error_message=error_message,
            product_id=product_id,
            barcode=barcode,
        )
    except Exception:  # noqa: BLE001
        return


def process_url_extraction_job(
    connection: sqlite3.Connection,
    job_id: str,
    extractor: Callable[[str], ProductProfile | None] = extract_product_from_url,
) -> DiscoveryJob | None:
    job = get_discovery_job(connection, job_id)
    if job is None:
        return None

    if job.job_type != JobType.url_extraction:
        msg = f"Job {job_id} is not a url_extraction job"
        raise ValueError(msg)

    update_discovery_job_status(connection, job_id, JobStatus.running)
    increment_discovery_job_attempt(connection, job_id)

    try:
        product = extractor(job.input_value)
        if product is None:
            _update_discovered_url_after_processing(connection, job, "not_found")
            return update_discovery_job_status(connection, job_id, JobStatus.not_found)

        if product.barcode:
            existing = get_product_by_barcode(connection, product.barcode)
        else:
            existing = None

        if existing is None:
            saved = create_product(connection, product)
        else:
            saved = update_product(
                connection,
                product.model_copy(update={"product_id": existing.product_id}),
            )
            if saved is None:
                error_message = "Failed to update existing product"
                _update_discovered_url_after_processing(
                    connection,
                    job,
                    "failed",
                    error_message=error_message,
                )
                return update_discovery_job_status(
                    connection,
                    job_id,
                    JobStatus.failed,
                    error_message=error_message,
                )

        for evidence in product.evidence:
            add_product_evidence(connection, saved.product_id or "", evidence)

        _update_discovered_url_after_processing(
            connection,
            job,
            "completed",
            product_id=saved.product_id,
            barcode=saved.barcode,
        )
        return update_discovery_job_status(
            connection,
            job_id,
            JobStatus.completed,
            result_product_id=saved.product_id,
        )
    except Exception as exc:  # noqa: BLE001
        error_message = f"URL extraction processing failed: {exc}"
        _update_discovered_url_after_processing(
            connection,
            job,
            "failed",
            error_message=error_message,
        )
        return update_discovery_job_status(
            connection,
            job_id,
            JobStatus.failed,
            error_message=error_message,
        )
