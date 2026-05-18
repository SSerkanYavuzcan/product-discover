import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.jobs import DiscoveryJob, JobPriority, JobStatus, JobType, create_discovery_job
from app.main import app
from app.models import ProductProfile, create_product
from app.sources import (
    ExtractionRun,
    SourceRegistry,
    create_extraction_run,
    create_source,
)
from app.storage.database import get_connection, initialize_database


def test_dashboard_activity_api(tmp_path) -> None:
    db_path = tmp_path / "dashboard_activity.db"
    initialize_database(str(db_path))

    def override_get_db_connection() -> Iterator[sqlite3.Connection]:
        connection = get_connection(str(db_path))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db_connection] = override_get_db_connection

    try:
        client = TestClient(app)

        response = client.get("/dashboard/activity")
        assert response.status_code == 200
        assert response.json()["count"] == 0
        assert response.json()["items"] == []

        with get_connection(str(db_path)) as connection:
            source_1 = create_source(
                connection,
                SourceRegistry(source_name="Source One", source_type="website", base_url="https://one.test"),
            )
            source_2 = create_source(
                connection,
                SourceRegistry(source_name="Source Two", source_type="website", base_url="https://two.test"),
            )
            create_extraction_run(
                connection,
                ExtractionRun(
                    run_id="run-completed",
                    source_id=source_1.source_id,
                    status="completed",
                    started_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 1, 1, 10, 5, tzinfo=UTC),
                    pages_seen=9,
                    products_found=3,
                ),
            )
            create_extraction_run(
                connection,
                ExtractionRun(
                    run_id="run-failed",
                    source_id=source_1.source_id,
                    status="failed",
                    started_at=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 1, 1, 11, 5, tzinfo=UTC),
                    pages_seen=4,
                    products_found=1,
                    error_message="boom",
                ),
            )
            create_discovery_job(
                connection,
                DiscoveryJob(
                    job_id="job-completed",
                    job_type=JobType.url_extraction,
                    status=JobStatus.completed,
                    priority=JobPriority.normal,
                    input_type="url",
                    input_value="https://one.test/p/1",
                    source_id=source_1.source_id,
                    result_product_id="product-result",
                    completed_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
                ),
            )
            create_discovery_job(
                connection,
                DiscoveryJob(
                    job_id="job-failed",
                    job_type=JobType.url_extraction,
                    status=JobStatus.failed,
                    priority=JobPriority.normal,
                    input_type="url",
                    input_value="https://one.test/p/2",
                    source_id=source_1.source_id,
                    error_message="bad scrape",
                    completed_at=datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
                ),
            )
            create_discovery_job(
                connection,
                DiscoveryJob(
                    job_id="job-other-source",
                    job_type=JobType.url_extraction,
                    status=JobStatus.pending,
                    priority=JobPriority.normal,
                    input_type="url",
                    input_value="https://two.test/p/1",
                    source_id=source_2.source_id,
                ),
            )
            create_product(
                connection,
                ProductProfile(
                    product_id="product-1",
                    product_name="Alpha Product",
                    status="discovered",
                    barcode="0001",
                    created_at=datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
                ),
            )
            create_product(
                connection,
                ProductProfile(
                    product_id="product-2",
                    product_name="Beta Product",
                    status="discovered",
                    barcode="0002",
                    created_at=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
                ),
            )

        response = client.get("/dashboard/activity")
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] > 0

        by_type = {item["event_type"]: item for item in payload["items"]}
        assert by_type["source_created"]["source_name"]
        assert by_type["sitemap_discovery_completed"]["message"].find("product URLs") >= 0
        assert by_type["sitemap_discovery_failed"]["message"].find("boom") >= 0
        assert by_type["job_completed"]["job_id"] == "job-completed"
        assert by_type["job_completed"]["product_id"] == "product-result"
        assert by_type["job_failed"]["message"].find("bad scrape") >= 0
        assert by_type["product_discovered"]["product_id"]
        assert by_type["product_discovered"]["message"].find("Product") >= 0

        times = [item["event_time"] for item in payload["items"]]
        assert times == sorted(times, reverse=True)

        limit_response = client.get("/dashboard/activity?limit=2")
        assert limit_response.status_code == 200
        assert limit_response.json()["count"] == 2
        assert len(limit_response.json()["items"]) == 2

        filtered = client.get(f"/dashboard/activity?source_id={source_1.source_id}")
        assert filtered.status_code == 200
        filtered_items = filtered.json()["items"]
        assert all(item["event_type"] != "product_discovered" for item in filtered_items)
        assert all(item["source_id"] == source_1.source_id for item in filtered_items)

        clamped = client.get("/dashboard/activity?limit=500")
        assert clamped.status_code == 200
        assert clamped.json()["limit"] == 100
    finally:
        app.dependency_overrides.clear()
