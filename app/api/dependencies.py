import sqlite3
from collections.abc import Callable, Iterator

from app.config import get_settings
from app.jobs.models import DiscoveryJob
from app.processing.barcode_job import process_barcode_lookup_job
from app.processing.dispatcher import process_discovery_job
from app.storage.postgres_adapter import PostgresConnectionAdapter
from app.storage.runtime import get_runtime_connection


def get_db_connection() -> Iterator[sqlite3.Connection | PostgresConnectionAdapter]:
    settings = get_settings()

    with get_runtime_connection(
        database_backend=settings.database_backend,
        database_path=settings.database_path,
        database_url=settings.database_url,
    ) as connection:
        yield connection


def get_barcode_job_processor() -> Callable[[sqlite3.Connection, str], DiscoveryJob | None]:
    return process_barcode_lookup_job


def get_discovery_job_processor() -> Callable[[sqlite3.Connection, str], DiscoveryJob | None]:
    return process_discovery_job
