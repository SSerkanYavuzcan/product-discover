import sqlite3
from pathlib import Path

import pytest

from app.jobs import (
    BatchJob,
    DiscoveryJob,
    JobStatus,
    JobType,
    create_batch_job,
    create_discovery_job,
    get_batch_job,
    get_discovery_job,
    increment_discovery_job_attempt,
    update_batch_job_counts,
    update_batch_job_status,
    update_discovery_job_status,
)
from app.storage import get_connection, initialize_database


@pytest.fixture
def db_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "jobs_repository.db"
    initialize_database(str(db_path))
    connection = get_connection(str(db_path))
    try:
        yield connection
    finally:
        connection.close()


def test_create_discovery_job_inserts_job(db_connection: sqlite3.Connection) -> None:
    job = DiscoveryJob(
        job_id="job-1",
        job_type=JobType.url_extraction,
        input_type="url",
        input_value="https://example.com",
    )

    created = create_discovery_job(db_connection, job)

    assert created.job_id == "job-1"


def test_get_discovery_job_returns_inserted_job(db_connection: sqlite3.Connection) -> None:
    job = DiscoveryJob(
        job_id="job-2",
        job_type=JobType.url_extraction,
        input_type="url",
        input_value="https://example.com/2",
    )
    create_discovery_job(db_connection, job)

    fetched = get_discovery_job(db_connection, "job-2")

    assert fetched is not None
    assert fetched.job_id == "job-2"


def test_get_discovery_job_missing_returns_none(db_connection: sqlite3.Connection) -> None:
    assert get_discovery_job(db_connection, "missing") is None


def test_duplicate_discovery_job_raises_integrity_error(db_connection: sqlite3.Connection) -> None:
    job = DiscoveryJob(
        job_id="job-dup",
        job_type=JobType.url_extraction,
        input_type="url",
        input_value="https://example.com",
    )
    create_discovery_job(db_connection, job)

    with pytest.raises(sqlite3.IntegrityError):
        create_discovery_job(db_connection, job)


def test_update_discovery_job_status_updates_fields(db_connection: sqlite3.Connection) -> None:
    job = DiscoveryJob(
        job_id="job-status",
        job_type=JobType.url_extraction,
        input_type="url",
        input_value="https://example.com",
    )
    create_discovery_job(db_connection, job)

    running = update_discovery_job_status(db_connection, "job-status", JobStatus.running)
    assert running is not None
    assert running.status == JobStatus.running
    assert running.started_at is not None

    completed = update_discovery_job_status(
        db_connection,
        "job-status",
        JobStatus.completed,
        result_product_id="product-1",
    )
    assert completed is not None
    assert completed.status == JobStatus.completed
    assert completed.completed_at is not None
    assert completed.result_product_id == "product-1"


def test_increment_discovery_job_attempt(db_connection: sqlite3.Connection) -> None:
    job = DiscoveryJob(
        job_id="job-attempt",
        job_type=JobType.url_extraction,
        input_type="url",
        input_value="https://example.com",
    )
    create_discovery_job(db_connection, job)

    updated = increment_discovery_job_attempt(db_connection, "job-attempt")

    assert updated is not None
    assert updated.attempt_count == 1


def test_create_batch_job_inserts_batch(db_connection: sqlite3.Connection) -> None:
    batch = BatchJob(batch_id="batch-1", batch_type=JobType.batch_barcode_ingestion)

    created = create_batch_job(db_connection, batch)

    assert created.batch_id == "batch-1"


def test_get_batch_job_returns_inserted_batch(db_connection: sqlite3.Connection) -> None:
    batch = BatchJob(batch_id="batch-2", batch_type=JobType.batch_barcode_ingestion)
    create_batch_job(db_connection, batch)

    fetched = get_batch_job(db_connection, "batch-2")

    assert fetched is not None
    assert fetched.batch_id == "batch-2"


def test_get_batch_job_missing_returns_none(db_connection: sqlite3.Connection) -> None:
    assert get_batch_job(db_connection, "missing") is None


def test_duplicate_batch_job_raises_integrity_error(db_connection: sqlite3.Connection) -> None:
    batch = BatchJob(batch_id="batch-dup", batch_type=JobType.batch_barcode_ingestion)
    create_batch_job(db_connection, batch)

    with pytest.raises(sqlite3.IntegrityError):
        create_batch_job(db_connection, batch)


def test_update_batch_job_counts_updates_only_provided_fields(
    db_connection: sqlite3.Connection,
) -> None:
    batch = BatchJob(
        batch_id="batch-counts",
        batch_type=JobType.batch_barcode_ingestion,
        pending_count=5,
        completed_count=1,
    )
    create_batch_job(db_connection, batch)

    updated = update_batch_job_counts(
        db_connection,
        "batch-counts",
        completed_count=4,
        failed_count=2,
    )

    assert updated is not None
    assert updated.pending_count == 5
    assert updated.completed_count == 4
    assert updated.failed_count == 2


def test_update_batch_job_status_updates_timestamps(db_connection: sqlite3.Connection) -> None:
    batch = BatchJob(batch_id="batch-status", batch_type=JobType.batch_barcode_ingestion)
    create_batch_job(db_connection, batch)

    running = update_batch_job_status(db_connection, "batch-status", JobStatus.running)
    assert running is not None
    assert running.started_at is not None

    completed = update_batch_job_status(db_connection, "batch-status", JobStatus.completed)
    assert completed is not None
    assert completed.completed_at is not None
