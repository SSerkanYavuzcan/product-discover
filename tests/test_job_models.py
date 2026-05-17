from datetime import datetime

import pytest
from pydantic import ValidationError

from app.jobs import BatchJob, BatchJobProgress, DiscoveryJob, JobPriority, JobStatus, JobType


def test_discovery_job_minimal_creation() -> None:
    job = DiscoveryJob(
        job_id="job-1",
        job_type=JobType.url_extraction,
        input_type="url",
        input_value="https://example.com/product",
    )

    assert job.status == JobStatus.pending
    assert job.priority == JobPriority.normal


def test_batch_job_minimal_creation() -> None:
    batch = BatchJob(batch_id="batch-1", batch_type=JobType.batch_barcode_ingestion)

    assert batch.status == JobStatus.pending
    assert batch.total_items == 0


def test_batch_job_progress_valid_creation() -> None:
    progress = BatchJobProgress(
        batch_id="batch-1",
        total_items=100,
        processed_items=40,
        progress_ratio=0.4,
        status=JobStatus.running,
    )

    assert progress.status == JobStatus.running


def test_invalid_attempt_count_raises() -> None:
    with pytest.raises(ValidationError):
        DiscoveryJob(
            job_id="job-1",
            job_type=JobType.url_extraction,
            input_type="url",
            input_value="https://example.com",
            attempt_count=-1,
        )


def test_invalid_max_attempts_raises() -> None:
    with pytest.raises(ValidationError):
        DiscoveryJob(
            job_id="job-1",
            job_type=JobType.url_extraction,
            input_type="url",
            input_value="https://example.com",
            max_attempts=0,
        )


def test_negative_counts_raise() -> None:
    with pytest.raises(ValidationError):
        BatchJob(batch_id="batch-1", batch_type=JobType.batch_barcode_ingestion, failed_count=-1)


def test_unique_items_greater_than_total_raises() -> None:
    with pytest.raises(ValidationError):
        BatchJob(
            batch_id="batch-1",
            batch_type=JobType.batch_barcode_ingestion,
            total_items=10,
            unique_items=11,
        )


def test_progress_ratio_out_of_range_raises() -> None:
    with pytest.raises(ValidationError):
        BatchJobProgress(
            batch_id="batch-1",
            total_items=100,
            processed_items=50,
            progress_ratio=-0.1,
            status=JobStatus.running,
        )

    with pytest.raises(ValidationError):
        BatchJobProgress(
            batch_id="batch-1",
            total_items=100,
            processed_items=50,
            progress_ratio=1.1,
            status=JobStatus.running,
        )


def test_processed_items_greater_than_total_raises() -> None:
    with pytest.raises(ValidationError):
        BatchJobProgress(
            batch_id="batch-1",
            total_items=10,
            processed_items=11,
            progress_ratio=0.5,
            status=JobStatus.running,
        )


def test_timestamps_auto_populated() -> None:
    job = DiscoveryJob(
        job_id="job-1",
        job_type=JobType.url_extraction,
        input_type="url",
        input_value="https://example.com",
    )
    batch = BatchJob(batch_id="batch-1", batch_type=JobType.batch_barcode_ingestion)

    assert isinstance(job.created_at, datetime)
    assert isinstance(job.updated_at, datetime)
    assert job.created_at.tzinfo is not None
    assert job.updated_at.tzinfo is not None
    assert isinstance(batch.created_at, datetime)
    assert isinstance(batch.updated_at, datetime)
    assert batch.created_at.tzinfo is not None
    assert batch.updated_at.tzinfo is not None


def test_enum_values_serialize_as_strings() -> None:
    job = DiscoveryJob(
        job_id="job-1",
        job_type=JobType.url_extraction,
        status=JobStatus.running,
        priority=JobPriority.high,
        input_type="url",
        input_value="https://example.com",
    )

    payload = job.model_dump(mode="json")

    assert payload["job_type"] == "url_extraction"
    assert payload["status"] == "running"
    assert payload["priority"] == "high"
