import sqlite3
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_barcode_job_processor, get_db_connection
from app.api.schemas import (
    BarcodeIngestionRequest,
    BarcodeIngestionResponse,
    JobProcessResponse,
    ProductReadResponse,
    UrlIngestionRequest,
    UrlIngestionResponse,
)
from app.config import get_settings
from app.ingestion.barcode import create_barcode_lookup_job
from app.ingestion.url import create_url_extraction_job
from app.jobs.models import DiscoveryJob
from app.models.repository import get_product, get_product_by_barcode

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
        Depends(get_barcode_job_processor),
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