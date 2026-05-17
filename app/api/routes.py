import sqlite3
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_db_connection, get_discovery_job_processor
from app.api.schemas import (
    BarcodeIngestionRequest,
    BarcodeIngestionResponse,
    DiscoveredUrlResponse,
    ExtractionRunResponse,
    JobProcessResponse,
    ProductReadResponse,
    SitemapDiscoveryRequest,
    SourceActiveStatusRequest,
    SourceRegistryCreateRequest,
    SourceRegistryResponse,
    UrlIngestionRequest,
    UrlIngestionResponse,
)
from app.config import get_settings
from app.discovery import discover_urls_from_source_sitemap
from app.ingestion.barcode import create_barcode_lookup_job
from app.ingestion.url import create_url_extraction_job
from app.jobs.models import DiscoveryJob
from app.models.repository import get_product, get_product_by_barcode
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
