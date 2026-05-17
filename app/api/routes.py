import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_db_connection
from app.api.schemas import BarcodeIngestionRequest, BarcodeIngestionResponse
from app.config import get_settings
from app.ingestion.barcode import create_barcode_lookup_job

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
