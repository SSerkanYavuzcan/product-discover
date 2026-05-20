import sqlite3
from collections.abc import Callable
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_db_connection, get_discovery_job_processor
from app.api.schemas import (
    BarcodeIngestionRequest,
    BarcodeIngestionResponse,
    DashboardActivityItemResponse,
    DashboardActivityResponse,
    DashboardSummaryResponse,
    DiscoveredUrlJobCreationRequest,
    DiscoveredUrlJobCreationResponse,
    DiscoveredUrlResponse,
    DiscoveredUrlRetryRequest,
    DiscoveredUrlRetryResponse,
    ExtractionRunResponse,
    JobProcessResponse,
    ProcessedJobItemResponse,
    ProcessManyJobsRequest,
    ProcessManyJobsResponse,
    ProcessNextBatchRequest,
    ProcessNextBatchResponse,
    ProductListResponse,
    ProductReadResponse,
    SitemapDiscoveryRequest,
    SourceActiveStatusRequest,
    SourceProcessingSummaryResponse,
    SourceRegistryCreateRequest,
    SourceRegistryResponse,
    SourceScraperCapabilityResponse,
    SourceScrapeRequest,
    SourceScrapeResponse,
    UrlIngestionRequest,
    UrlIngestionResponse,
)
from app.config import get_settings
from app.dashboard import get_dashboard_activity, get_dashboard_summary
from app.discovery import discover_urls_from_source_sitemap
from app.ingestion.barcode import create_barcode_lookup_job
from app.ingestion.url import create_url_extraction_job
from app.jobs.models import DiscoveryJob
from app.models.repository import get_product, get_product_by_barcode, list_products
from app.processing.discovered_url_jobs import (
    create_url_extraction_jobs_from_discovered_urls,
)
from app.processing.scraper_job import persist_scraped_products
from app.scrapers.registry import get_scraper_for_source
from app.sources import (
    SourceRegistry,
    create_source,
    get_source,
    list_active_sources,
    list_discovered_urls_by_source,
    update_source_active_status,
)
from app.sources.repository import (
    delete_all_system_data,
    delete_source_completely,
    get_source_processing_summary_counts,
    reset_discovered_urls_for_retry,
)

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name}


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK,
)
def read_dashboard_summary(
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> DashboardSummaryResponse:
    summary = get_dashboard_summary(connection)
    return DashboardSummaryResponse.model_validate(asdict(summary))


@router.get(
    "/dashboard/activity",
    response_model=DashboardActivityResponse,
    status_code=status.HTTP_200_OK,
)
def read_dashboard_activity(
    limit: int = 50,
    source_id: str | None = None,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)] = None,
) -> DashboardActivityResponse:
    normalized_limit = 50 if limit <= 0 else min(limit, 100)
    activity_items = get_dashboard_activity(connection, limit=limit, source_id=source_id)
    items = [DashboardActivityItemResponse.model_validate(asdict(item)) for item in activity_items]
    return DashboardActivityResponse(
        items=items,
        count=len(items),
        limit=normalized_limit,
        source_id=source_id,
    )


@router.post(
    "/ingest/barcode",
    status_code=status.HTTP_201_CREATED,
    response_model=BarcodeIngestionResponse,
)
def ingest_barcode(
    payload: BarcodeIngestionRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> BarcodeIngestionResponse:
    try:
        job = create_barcode_lookup_job(
            connection=connection,
            barcode=payload.barcode,
            priority=payload.priority,
            batch_id=payload.batch_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return BarcodeIngestionResponse.model_validate(job.model_dump())


@router.post(
    "/ingest/url",
    status_code=status.HTTP_201_CREATED,
    response_model=UrlIngestionResponse,
)
def ingest_url(
    payload: UrlIngestionRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> UrlIngestionResponse:
    try:
        job = create_url_extraction_job(
            connection=connection,
            url=payload.url,
            priority=payload.priority,
            batch_id=payload.batch_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return UrlIngestionResponse.model_validate(job.model_dump())


@router.post(
    "/jobs/process-many",
    response_model=ProcessManyJobsResponse,
    status_code=status.HTTP_200_OK,
)
def process_many_jobs(
    payload: ProcessManyJobsRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
    processor: Annotated[
        Callable[[sqlite3.Connection, str], DiscoveryJob | None],
        Depends(get_discovery_job_processor),
    ],
) -> ProcessManyJobsResponse:
    requested_count = len(payload.job_ids)
    selected_job_ids = payload.job_ids[: payload.max_jobs]
    results: list[ProcessedJobItemResponse] = []

    for selected_job_id in selected_job_ids:
        try:
            job = processor(connection, selected_job_id)
        except ValueError as exc:
            results.append(
                ProcessedJobItemResponse(
                    job_id=selected_job_id,
                    status="failed",
                    error_message=str(exc),
                )
            )
            continue

        if job is None:
            results.append(
                ProcessedJobItemResponse(
                    job_id=selected_job_id,
                    status="not_found",
                    error_message=f"Discovery job not found: {selected_job_id}",
                )
            )
            continue

        results.append(
            ProcessedJobItemResponse(
                job_id=job.job_id,
                status=job.status,
                job_type=job.job_type,
                result_product_id=job.result_product_id,
                error_message=job.error_message,
            )
        )

    processed_count = len(selected_job_ids)
    return ProcessManyJobsResponse(
        requested_count=requested_count,
        processed_count=processed_count,
        skipped_count=requested_count - processed_count,
        results=results,
    )


@router.post(
    "/jobs/{job_id}/process",
    response_model=JobProcessResponse,
    status_code=status.HTTP_200_OK,
)
def process_job(
    job_id: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
    processor: Annotated[
        Callable[[sqlite3.Connection, str], DiscoveryJob | None],
        Depends(get_discovery_job_processor),
    ],
) -> JobProcessResponse:
    try:
        job = processor(connection, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Discovery job not found: {job_id}",
        )

    return JobProcessResponse.model_validate(job.model_dump())


@router.post(
    "/sources",
    status_code=status.HTTP_201_CREATED,
    response_model=SourceRegistryResponse,
)
def create_registry_source(
    payload: SourceRegistryCreateRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> SourceRegistryResponse:
    source = SourceRegistry(**payload.model_dump())
    created = create_source(connection, source)
    return SourceRegistryResponse.model_validate(created.model_dump())


@router.get(
    "/sources",
    response_model=list[SourceRegistryResponse],
    status_code=status.HTTP_200_OK,
)
def read_active_sources(
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> list[SourceRegistryResponse]:
    sources = list_active_sources(connection)
    return [SourceRegistryResponse.model_validate(source.model_dump()) for source in sources]


@router.post(
    "/sources/{source_id}/discover-sitemap",
    response_model=ExtractionRunResponse,
    status_code=status.HTTP_200_OK,
)
def discover_source_sitemap(
    source_id: str,
    payload: SitemapDiscoveryRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> ExtractionRunResponse:
    run = discover_urls_from_source_sitemap(
        connection=connection,
        source_id=source_id,
        max_child_sitemaps=payload.max_child_sitemaps,
        product_only=payload.product_only,
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    return ExtractionRunResponse.model_validate(run.model_dump())


@router.get(
    "/sources/{source_id}/scraper-capability",
    response_model=SourceScraperCapabilityResponse,
    status_code=status.HTTP_200_OK,
)
def read_source_scraper_capability(
    source_id: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> SourceScraperCapabilityResponse:
    source = get_source(connection, source_id)
    if source is None:
        return SourceScraperCapabilityResponse(source_id=source_id, has_custom_scraper=False)
    scraper = get_scraper_for_source(source)
    return SourceScraperCapabilityResponse(
        source_id=source_id,
        has_custom_scraper=scraper is not None,
        scraper_name=scraper.__class__.__name__ if scraper else None,
        supported_domain=(
            scraper.domain_patterns[0]
            if scraper and scraper.domain_patterns
            else None
        ),
    )


@router.post(
    "/sources/{source_id}/scrape",
    response_model=SourceScrapeResponse,
    status_code=status.HTTP_200_OK,
)
def scrape_source(
    source_id: str,
    payload: SourceScrapeRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> SourceScrapeResponse:
    source = get_source(connection, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    scraper = None if payload.force_generic else get_scraper_for_source(source)
    if scraper is None:
        return SourceScrapeResponse(
            source_id=source_id,
            source_name=source.source_name,
            method="no_custom_scraper",
            scraper_name=None,
            requested_limit=payload.limit,
            scraped_count=0,
            persisted_count=0,
            skipped_count=0,
            error_count=0,
            errors=[],
        )

    scraped_products = scraper.scrape(source=source, limit=payload.limit)
    persisted_count, skipped_count, persist_errors = persist_scraped_products(
        connection=connection,
        source=source,
        scraped_products=scraped_products,
    )
    return SourceScrapeResponse(
        source_id=source_id,
        source_name=source.source_name,
        method="custom_scraper",
        scraper_name=scraper.__class__.__name__,
        requested_limit=payload.limit,
        scraped_count=len(scraped_products),
        persisted_count=persisted_count,
        skipped_count=skipped_count,
        error_count=len(persist_errors),
        errors=persist_errors,
    )


@router.get(
    "/sources/{source_id}/discovered-urls",
    response_model=list[DiscoveredUrlResponse],
    status_code=status.HTTP_200_OK,
)
def read_discovered_urls_by_source(
    source_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 100,
    offset: int = 0,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)] = None,
) -> list[DiscoveredUrlResponse]:
    source = get_source(connection, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    discovered_urls = list_discovered_urls_by_source(
        connection=connection,
        source_id=source_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [DiscoveredUrlResponse.model_validate(url.model_dump()) for url in discovered_urls]


@router.post(
    "/sources/{source_id}/discovered-urls/create-jobs",
    response_model=DiscoveredUrlJobCreationResponse,
    status_code=status.HTTP_200_OK,
)
def create_jobs_from_discovered_urls(
    source_id: str,
    payload: DiscoveredUrlJobCreationRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> DiscoveredUrlJobCreationResponse:
    result = create_url_extraction_jobs_from_discovered_urls(
        connection=connection,
        source_id=source_id,
        status=payload.status,
        limit=payload.limit,
        priority=payload.priority,
        batch_id=payload.batch_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    return DiscoveredUrlJobCreationResponse(
        source_id=result.source_id,
        status_filter=result.status_filter,
        requested_limit=result.requested_limit,
        created_count=result.created_count,
        skipped_count=result.skipped_count,
        job_ids=result.job_ids,
    )




@router.post(
    "/sources/{source_id}/discovered-urls/retry",
    response_model=DiscoveredUrlRetryResponse,
    status_code=status.HTTP_200_OK,
)
def retry_discovered_urls(
    source_id: str,
    payload: DiscoveredUrlRetryRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> DiscoveredUrlRetryResponse:
    source = get_source(connection, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    allowed_statuses = {"failed", "not_found", "queued"}
    unsupported_statuses = sorted(set(payload.statuses) - allowed_statuses)
    if unsupported_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Unsupported retry status values: "
                + ", ".join(unsupported_statuses)
                + ". Allowed: failed, not_found, queued"
            ),
        )

    result = reset_discovered_urls_for_retry(
        connection=connection,
        source_id=source_id,
        statuses=payload.statuses,
        limit=payload.limit,
    )
    return DiscoveredUrlRetryResponse.model_validate(result)

@router.get(
    "/sources/{source_id}/processing-summary",
    response_model=SourceProcessingSummaryResponse,
    status_code=status.HTTP_200_OK,
)
def read_source_processing_summary(
    source_id: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> SourceProcessingSummaryResponse:
    source = get_source(connection, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    summary = get_source_processing_summary_counts(connection, source_id)
    return SourceProcessingSummaryResponse(**summary)


@router.post(
    "/sources/{source_id}/process-next-batch",
    response_model=ProcessNextBatchResponse,
    status_code=status.HTTP_200_OK,
)
def process_next_source_batch(
    source_id: str,
    payload: ProcessNextBatchRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
    processor: Annotated[
        Callable[[sqlite3.Connection, str], DiscoveryJob | None],
        Depends(get_discovery_job_processor),
    ] = None,
) -> ProcessNextBatchResponse:
    source = get_source(connection, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    creation_result = create_url_extraction_jobs_from_discovered_urls(
        connection=connection,
        source_id=source_id,
        status=payload.status,
        limit=payload.batch_size,
        priority=payload.priority,
        batch_id=payload.batch_id,
    )
    if creation_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    results: list[ProcessedJobItemResponse] = []
    completed_count = 0
    failed_count = 0
    not_found_count = 0

    for selected_job_id in creation_result.job_ids:
        try:
            job = processor(connection, selected_job_id)
        except ValueError as exc:
            failed_count += 1
            results.append(
                ProcessedJobItemResponse(
                    job_id=selected_job_id,
                    status="failed",
                    error_message=str(exc),
                )
            )
            continue

        if job is None:
            not_found_count += 1
            results.append(
                ProcessedJobItemResponse(
                    job_id=selected_job_id,
                    status="not_found",
                    error_message=f"Discovery job not found: {selected_job_id}",
                )
            )
            continue

        job_status = job.status.value
        if job_status == "completed":
            completed_count += 1
        if job_status in {"failed", "not_found"}:
            failed_count += 1
        if job_status == "not_found":
            not_found_count += 1

        results.append(
            ProcessedJobItemResponse(
                job_id=job.job_id,
                status=job.status,
                job_type=job.job_type,
                result_product_id=job.result_product_id,
                error_message=job.error_message,
            )
        )

    summary = get_source_processing_summary_counts(connection, source_id)
    return ProcessNextBatchResponse(
        source_id=source_id,
        requested_batch_size=payload.batch_size,
        created_count=creation_result.created_count,
        processed_count=len(creation_result.job_ids),
        completed_count=completed_count,
        failed_count=failed_count,
        not_found_count=not_found_count,
        skipped_count=creation_result.skipped_count,
        remaining_urls=summary["remaining_urls"],
        results=results,
    )


@router.get(
    "/sources/{source_id}",
    response_model=SourceRegistryResponse,
    status_code=status.HTTP_200_OK,
)
def read_source(
    source_id: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> SourceRegistryResponse:
    source = get_source(connection, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    return SourceRegistryResponse.model_validate(source.model_dump())


@router.patch(
    "/sources/{source_id}/active",
    response_model=SourceRegistryResponse,
    status_code=status.HTTP_200_OK,
)
def patch_source_active_status(
    source_id: str,
    payload: SourceActiveStatusRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> SourceRegistryResponse:
    source = update_source_active_status(connection, source_id, payload.is_active)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    return SourceRegistryResponse.model_validate(source.model_dump())


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_200_OK,
)
def delete_registry_source_completely(
    source_id: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> dict[str, str]:
    """Hard deletes a source and all its associated data."""
    success = delete_source_completely(connection, source_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    return {"status": "deleted", "source_id": source_id}


@router.delete(
    "/system/reset",
    status_code=status.HTTP_200_OK,
)
def reset_entire_system(
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> dict[str, str]:
    """Wipes all product discover data from the database."""
    delete_all_system_data(connection)
    return {"status": "system_reset_successful"}


@router.get(
    "/products",
    response_model=ProductListResponse,
    status_code=status.HTTP_200_OK,
)
def read_products(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 100,
    offset: int = 0,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)] = None,
) -> ProductListResponse:
    normalized_limit = 100 if limit <= 0 else min(limit, 500)
    normalized_offset = max(offset, 0)
    products = list_products(
        connection=connection,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    items = [ProductReadResponse.model_validate(product.model_dump()) for product in products]
    return ProductListResponse(
        items=items,
        count=len(items),
        limit=normalized_limit,
        offset=normalized_offset,
    )


@router.get(
    "/products/by-barcode/{barcode}",
    response_model=ProductReadResponse,
    status_code=status.HTTP_200_OK,
)
def read_product_by_barcode(
    barcode: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> ProductReadResponse:
    product = get_product_by_barcode(connection, barcode)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product not found for barcode: {barcode}",
        )

    return ProductReadResponse.model_validate(product.model_dump())


@router.get(
    "/products/{product_id}",
    response_model=ProductReadResponse,
    status_code=status.HTTP_200_OK,
)
def read_product(
    product_id: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> ProductReadResponse:
    product = get_product(connection, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product not found: {product_id}",
        )

    return ProductReadResponse.model_validate(product.model_dump())
