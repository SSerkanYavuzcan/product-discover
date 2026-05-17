import sqlite3
from pathlib import Path

import pytest

from app.ingestion.barcode import (
    create_barcode_lookup_job,
    is_valid_barcode,
    normalize_barcode,
)
from app.jobs.models import JobPriority, JobStatus, JobType
from app.jobs.repository import get_discovery_job
from app.storage import get_connection, initialize_database


@pytest.fixture
def db_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "barcode_ingestion.db"
    initialize_database(str(db_path))
    connection = get_connection(str(db_path))
    try:
        yield connection
    finally:
        connection.close()


def test_normalize_barcode_strips_whitespace() -> None:
    assert normalize_barcode(" 3017620422003 ") == "3017620422003"


def test_normalize_barcode_removes_spaces() -> None:
    assert normalize_barcode("3017 6204 22003") == "3017620422003"


def test_normalize_barcode_removes_hyphens() -> None:
    assert normalize_barcode("3017-6204-22003") == "3017620422003"


def test_is_valid_barcode_accepts_common_gtin_lengths() -> None:
    assert is_valid_barcode("12345678") is True
    assert is_valid_barcode("123456789012") is True
    assert is_valid_barcode("1234567890123") is True
    assert is_valid_barcode("12345678901234") is True


def test_is_valid_barcode_rejects_non_digits() -> None:
    assert is_valid_barcode("1234abcd5678") is False


def test_is_valid_barcode_rejects_invalid_lengths() -> None:
    assert is_valid_barcode("1234567") is False
    assert is_valid_barcode("123456789") is False


def test_create_barcode_lookup_job_creates_and_stores_job(
    db_connection: sqlite3.Connection,
) -> None:
    created = create_barcode_lookup_job(
        db_connection,
        barcode="3017-6204-22003",
        priority=JobPriority.high,
        batch_id="batch-123",
    )

    assert created.job_type == JobType.barcode_lookup
    assert created.status == JobStatus.pending
    assert created.input_type == "barcode"
    assert created.input_value == "3017620422003"
    assert created.priority == JobPriority.high
    assert created.batch_id == "batch-123"

    fetched = get_discovery_job(db_connection, created.job_id)
    assert fetched is not None
    assert fetched.job_id == created.job_id
    assert fetched.input_value == "3017620422003"


def test_create_barcode_lookup_job_raises_for_invalid_barcode(
    db_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(ValueError, match="Invalid barcode"):
        create_barcode_lookup_job(db_connection, barcode="abc-123")
