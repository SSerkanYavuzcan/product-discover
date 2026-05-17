import sqlite3
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_db_connection, get_discovery_job_processor
from app.api.schemas import (
    BarcodeIngestionRequest,
    BarcodeIngestionResponse,
    JobProcessResponse,
    ProductReadResponse,
    SourceActiveStatusRequest,
    SourceRegistryCreateRequest,
    SourceRegistryResponse,
    UrlIngestionRequest,
    UrlIngestionResponse,
)
from app.config import get_settings
from app.ingestion.barcode import create_barcode_lookup_job
from app.ingestion.url import create_url_extraction_job
from app.jobs.models import DiscoveryJob
from app.models.repository import get_product, get_product_by_barcode
from app.sources import (
    SourceRegistry,
    create_source,
    get_source,
    list_active_sources,
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
    "/sources",
    status_code=status.HTTP_201_CREATED,
    response_model=SourceRegistryResponse,
)
def create_source_registry(
    payload: SourceRegistryCreateRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> SourceRegistryResponse:
    source = create_source(connection, SourceRegistry.model_validate(payload.model_dump()))
    return SourceRegistryResponse.model_validate(source.model_dump())


@router.get("/sources", response_model=list[SourceRegistryResponse])
def get_active_sources(
    connection: Annotated[sqlite3.Connection, Depends(get_db_connection)],
) -> list[SourceRegistryResponse]:
    sources = list_active_sources(connection)
    return [SourceRegistryResponse.model_validate(source.model_dump()) for source in sources]


@router.get("/sources/{source_id}", response_model=SourceRegistryResponse)
def get_source_registry(
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


@router.patch("/sources/{source_id}/active", response_model=SourceRegistryResponse)
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