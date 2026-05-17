import pytest

from app.ingestion.barcode import (
    create_barcode_lookup_job,
    is_valid_barcode,
    normalize_barcode,
)
from app.jobs.models import JobPriority, JobStatus, JobType
from app.jobs.repository import get_discovery_job
from app.storage.database import get_connection, initialize_database


def test_normalize_barcode_strips_whitespace() -> None:
    assert normalize_barcode(" 3017620422003 ") == "3017620422003"


def test_normalize_barcode_removes_spaces() -> None:
    assert normalize_barcode("3017 6204 22003") == "3017620422003"


def test_normalize_barcode_removes_hyphens() -> None:
    assert normalize_barcode("3017-6204-22003") == "3017620422003"


@pytest.mark.parametrize("barcode", ["12345678", "123456789012", "1234567890123", "12345678901234"])
def test_is_valid_barcode_accepts_valid_gtin_lengths(barcode: str) -> None:
    assert is_valid_barcode(barcode)


@pytest.mark.parametrize("barcode", ["1234abcd", "1234 56x8", "12-34-abcd"])
def test_is_valid_barcode_rejects_non_digits(barcode: str) -> None:
    assert not is_valid_barcode(barcode)


@pytest.mark.parametrize("barcode", ["1234567", "123456789", "12345678901", "123456789012345"])
def test_is_valid_barcode_rejects_invalid_lengths(barcode: str) -> None:
    assert not is_valid_barcode(barcode)


def test_create_barcode_lookup_job_creates_and_stores_job(tmp_path) -> None:
    db_path = tmp_path / "barcode_jobs.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        created = create_barcode_lookup_job(
            connection=connection,
            barcode=" 3017-6204 22003 ",
            priority=JobPriority.high,
            batch_id="batch-123",
        )
        fetched = get_discovery_job(connection, created.job_id)

    assert created.job_type == JobType.barcode_lookup
    assert created.status == JobStatus.pending
    assert created.input_type == "barcode"
    assert created.input_value == "3017620422003"
    assert created.priority == JobPriority.high
    assert created.batch_id == "batch-123"

    assert fetched is not None
    assert fetched.job_id == created.job_id
    assert fetched.input_value == "3017620422003"


def test_create_barcode_lookup_job_raises_for_invalid_barcode(tmp_path) -> None:
    db_path = tmp_path / "barcode_jobs.db"
    initialize_database(str(db_path))

    with (
        get_connection(str(db_path)) as connection,
        pytest.raises(ValueError, match="Invalid barcode"),
    ):
        create_barcode_lookup_job(connection=connection, barcode="abc-123")
