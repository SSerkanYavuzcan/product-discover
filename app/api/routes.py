import sqlite3
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_db_connection, get_discovery_job_processor
from app.api.schemas import (
    BarcodeIngestionRequest,
    BarcodeIngestionResponse,
    DashboardSummaryResponse,
    DiscoveredUrlJobCreationRequest,
    DiscoveredUrlJobCreationResponse,
    DiscoveredUrlResponse,
    ExtractionRunResponse,
    JobProcessResponse,
    ProcessedJobItemResponse,
    ProcessManyJobsRequest,
    ProcessManyJobsResponse,
    ProductListResponse,
    ProductReadResponse,
    SitemapDiscoveryRequest,
    SourceActiveStatusRequest,
    SourceRegistryCreateRequest,
    SourceRegistryResponse,
    UrlIngestionRequest,
    UrlIngestionResponse,
)
from app.config import get_settings
from app.dashboard import get_dashboard_summary
from app.discovery import discover_urls_from_source_sitemap
from app.ingestion.barcode import create_barcode_lookup_job
from app.ingestion.url import create_url_extraction_job
from app.jobs.models import DiscoveryJob
from app.models.repository import get_product, get_product_by_barcode, list_products
from app.processing.discovered_url_jobs import create_url_extraction_jobs_from_discovered_urls
from app.sources import (
    SourceRegistry,
    create_source,
    get_source,
    list_active_sources,
    list_discovered_urls_by_source,
    update_source_active_status,
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
    return DashboardSummaryResponse.model_validate(summary)
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
