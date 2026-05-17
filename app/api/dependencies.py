import sqlite3
from collections.abc import Callable, Iterator

from app.config import get_settings
from app.jobs.models import DiscoveryJob
from app.processing.barcode_job import process_barcode_lookup_job
from app.storage.database import get_connection, initialize_database


def get_db_connection() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    initialize_database(settings.database_path)

    connection = get_connection(settings.database_path)
    try:
        yield connection
    finally:
        connection.close()


def get_barcode_job_processor() -> Callable[[sqlite3.Connection, str], DiscoveryJob | None]:
    return process_barcode_lookup_job