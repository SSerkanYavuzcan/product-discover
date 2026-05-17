from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.jobs.models import DiscoveryJob, JobPriority, JobStatus, JobType
from app.jobs.repository import create_discovery_job
from app.models import ConfidenceScore, ProductProfile, SourceEvidence
from app.models.repository import get_product_by_barcode
from app.processing.barcode_job import process_barcode_lookup_job
from app.storage.database import get_connection, initialize_database


def _make_job(job_type: JobType = JobType.barcode_lookup) -> DiscoveryJob:
    return DiscoveryJob(
        job_id=str(uuid4()),
        job_type=job_type,
        status=JobStatus.pending,
        priority=JobPriority.normal,
        input_type="barcode",
        input_value="3017620422003",
    )


def _make_profile(barcode: str, name: str = "Nut Spread") -> ProductProfile:
    return ProductProfile(
        barcode=barcode,
        gtin=barcode,
        product_name=name,
        brand="Brand A",
        category="Spreads",
        status="discovered",
        confidence=ConfidenceScore(overall=0.8, field_scores={"product_name": 0.9}),
        evidence=[
            SourceEvidence(
                source_name="Open Food Facts",
                source_type="open_database",
                source_url="https://world.openfoodfacts.org/api/v2/product/3017620422003.json",
                field_name="product_name",
                raw_value="Nut Spread",
                normalized_value=name,
                confidence=0.9,
                extracted_at=datetime.now(UTC),
            )
        ],
    )


def test_process_returns_none_for_missing_job(tmp_path) -> None:
    db_path = tmp_path / "processor.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        assert process_barcode_lookup_job(connection, "missing") is None


def test_process_raises_for_non_barcode_job(tmp_path) -> None:
    db_path = tmp_path / "processor.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        job = create_discovery_job(connection, _make_job(JobType.url_extraction))
        with pytest.raises(ValueError, match="not a barcode_lookup"):
            process_barcode_lookup_job(connection, job.job_id)


def test_process_marks_not_found_when_fetcher_returns_none(tmp_path) -> None:
    db_path = tmp_path / "processor.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        job = create_discovery_job(connection, _make_job())
        updated = process_barcode_lookup_job(connection, job.job_id, fetcher=lambda barcode: None)

    assert updated is not None
    assert updated.status == JobStatus.not_found
    assert updated.attempt_count == 1


def test_process_completes_and_saves_product_and_evidence(tmp_path) -> None:
    db_path = tmp_path / "processor.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        job = create_discovery_job(connection, _make_job())
        updated = process_barcode_lookup_job(
            connection,
            job.job_id,
            fetcher=lambda barcode: _make_profile(barcode),
        )
        product = get_product_by_barcode(connection, "3017620422003")

    assert updated is not None
    assert updated.status == JobStatus.completed
    assert updated.result_product_id is not None
    assert updated.attempt_count == 1

    assert product is not None
    assert product.product_id == updated.result_product_id
    assert product.evidence


def test_process_updates_existing_product_instead_of_duplicating(tmp_path) -> None:
    db_path = tmp_path / "processor.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        first_job = create_discovery_job(connection, _make_job())
        first = process_barcode_lookup_job(
            connection,
            first_job.job_id,
            fetcher=lambda barcode: _make_profile(barcode, "Original Name"),
        )

        second_job = create_discovery_job(
            connection,
            _make_job(),
        )
        second = process_barcode_lookup_job(
            connection,
            second_job.job_id,
            fetcher=lambda barcode: _make_profile(barcode, "Updated Name"),
        )
        product = get_product_by_barcode(connection, "3017620422003")

    assert first is not None and second is not None
    assert first.result_product_id == second.result_product_id
    assert product is not None
    assert product.product_name == "Updated Name"


def test_process_marks_failed_when_fetcher_raises(tmp_path) -> None:
    db_path = tmp_path / "processor.db"
    initialize_database(str(db_path))

    def exploding_fetcher(barcode: str) -> ProductProfile | None:
        raise RuntimeError(f"boom for {barcode}")

    with get_connection(str(db_path)) as connection:
        job = create_discovery_job(connection, _make_job())
        updated = process_barcode_lookup_job(connection, job.job_id, fetcher=exploding_fetcher)

    assert updated is not None
    assert updated.status == JobStatus.failed
    assert updated.attempt_count == 1
    assert updated.error_message is not None
    assert "Barcode lookup processing failed" in updated.error_message
