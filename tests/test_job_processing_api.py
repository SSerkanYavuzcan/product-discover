import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection, get_discovery_job_processor
from app.jobs.models import DiscoveryJob, JobPriority, JobStatus, JobType
from app.jobs.repository import create_discovery_job, update_discovery_job_status
from app.main import app
from app.models import ConfidenceScore, ProductProfile, SourceEvidence
from app.models.repository import create_product, get_product_by_barcode
from app.processing.barcode_job import process_barcode_lookup_job
from app.storage.database import get_connection, initialize_database


def _create_barcode_job(connection: sqlite3.Connection) -> DiscoveryJob:
    return create_discovery_job(
        connection,
        DiscoveryJob(
            job_id=str(uuid4()),
            job_type=JobType.barcode_lookup,
            status=JobStatus.pending,
            priority=JobPriority.normal,
            input_type="barcode",
            input_value="3017620422003",
        ),
    )


def _override_db(db_path: str) -> Callable[[], Iterator[sqlite3.Connection]]:
    def override() -> Iterator[sqlite3.Connection]:
        with get_connection(db_path) as connection:
            yield connection

    return override


def test_process_job_success(tmp_path) -> None:
    db_path = tmp_path / "jobs_api.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        job = _create_barcode_job(connection)

    def fake_fetcher(barcode: str) -> ProductProfile | None:
        return ProductProfile(
            barcode=barcode,
            gtin=barcode,
            product_name="Nut Spread",
            brand="Brand A",
            status="discovered",
            confidence=ConfidenceScore(overall=0.9),
            evidence=[
                SourceEvidence(
                    source_name="Open Food Facts",
                    source_type="open_database",
                    source_url="https://example.test",
                    field_name="product_name",
                    raw_value="Nut Spread",
                    normalized_value="Nut Spread",
                    confidence=0.9,
                    extracted_at=datetime.now(UTC),
                )
            ],
        )

    def fake_processor(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        return process_barcode_lookup_job(connection, job_id, fetcher=fake_fetcher)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: fake_processor
    try:
        client = TestClient(app)
        response = client.post(f"/jobs/{job.job_id}/process")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["job_type"] == "barcode_lookup"
    assert payload["attempt_count"] == 1
    assert payload["result_product_id"] is not None

    with get_connection(str(db_path)) as connection:
        product = get_product_by_barcode(connection, "3017620422003")
    assert product is not None


def test_process_job_missing_returns_404(tmp_path) -> None:
    db_path = tmp_path / "jobs_api.db"
    initialize_database(str(db_path))

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    try:
        client = TestClient(app)
        response = client.post("/jobs/missing-job/process")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_process_job_invalid_type_returns_400(tmp_path) -> None:
    db_path = tmp_path / "jobs_api.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        invalid_job = create_discovery_job(
            connection,
            DiscoveryJob(
                job_id=str(uuid4()),
                job_type=JobType.url_extraction,
                status=JobStatus.pending,
                priority=JobPriority.normal,
                input_type="url",
                input_value="https://example.test",
            ),
        )

    def invalid_processor(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        msg = "Job is not a barcode_lookup job"
        raise ValueError(msg)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: invalid_processor
    try:
        client = TestClient(app)
        response = client.post(f"/jobs/{invalid_job.job_id}/process")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "barcode_lookup" in response.json()["detail"]


def test_process_job_not_found_result(tmp_path) -> None:
    db_path = tmp_path / "jobs_api.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        job = _create_barcode_job(connection)

    def processor_not_found(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        return process_barcode_lookup_job(connection, job_id, fetcher=lambda barcode: None)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: processor_not_found
    try:
        client = TestClient(app)
        response = client.post(f"/jobs/{job.job_id}/process")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"


def test_process_job_failed_result(tmp_path) -> None:
    db_path = tmp_path / "jobs_api.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        job = _create_barcode_job(connection)

    def raising_fetcher(barcode: str) -> ProductProfile | None:
        raise RuntimeError(f"boom {barcode}")

    def processor_failed(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        return process_barcode_lookup_job(connection, job_id, fetcher=raising_fetcher)

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: processor_failed
    try:
        client = TestClient(app)
        response = client.post(f"/jobs/{job.job_id}/process")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error_message"] is not None


def test_process_url_job_success(tmp_path) -> None:
    db_path = tmp_path / "jobs_api.db"
    initialize_database(str(db_path))
    with get_connection(str(db_path)) as connection:
        job = create_discovery_job(
            connection,
            DiscoveryJob(
                job_id=str(uuid4()),
                job_type=JobType.url_extraction,
                status=JobStatus.pending,
                priority=JobPriority.normal,
                input_type="url",
                input_value="https://example.com/product-page",
            ),
        )

    def url_processor(connection: sqlite3.Connection, job_id: str) -> DiscoveryJob | None:
        job_obj = connection.execute(
            "SELECT * FROM discovery_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if job_obj is None:
            return None

        product = create_product(
            connection,
            ProductProfile(
                barcode="0123456789012",
                gtin="0123456789012",
                product_name="URL Product",
                brand="Brand U",
                status="discovered",
                confidence=ConfidenceScore(overall=0.8),
                evidence=[
                    SourceEvidence(
                        source_name="example.com",
                        source_type="product_page",
                        source_url="https://example.com/product-page",
                        field_name="product_name",
                        raw_value="URL Product",
                        normalized_value="URL Product",
                        confidence=0.8,
                        extracted_at=datetime.now(UTC),
                    )
                ],
            ),
        )
        return update_discovery_job_status(
            connection,
            job_id,
            JobStatus.completed,
            result_product_id=product.product_id,
        )

    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    app.dependency_overrides[get_discovery_job_processor] = lambda: url_processor
    try:
        client = TestClient(app)
        response = client.post(f"/jobs/{job.job_id}/process")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["job_type"] == "url_extraction"
    assert payload["result_product_id"] is not None

    with get_connection(str(db_path)) as connection:
        product = get_product_by_barcode(connection, "0123456789012")
    assert product is not None
