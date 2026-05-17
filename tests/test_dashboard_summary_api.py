import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.jobs import DiscoveryJob, JobPriority, JobStatus, JobType, create_discovery_job
from app.main import app
from app.models import ProductProfile, create_product
from app.sources import (
    DiscoveredUrl,
    ExtractionRun,
    SourceRegistry,
    create_discovered_url,
    create_extraction_run,
    create_source,
)
from app.storage.database import get_connection, initialize_database


def test_dashboard_summary_api(tmp_path) -> None:
    db_path = tmp_path / "dashboard_summary.db"
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

        # A) Empty summary returns zeros
        response = client.get("/dashboard/summary")
        assert response.status_code == 200
        payload = response.json()
        assert payload["sources"]["total_sources"] == 0
        assert payload["products"]["total_products"] == 0
        assert payload["urls"]["total_discovered_urls"] == 0
        assert payload["jobs"]["total_jobs"] == 0
        assert payload["jobs"]["success_rate"] == 0.0
        assert payload["latest_run"] is None

        with get_connection(str(db_path)) as connection:
            # B) Sources
            source_active = create_source(
                connection,
                SourceRegistry(source_name="Active", source_type="website", base_url="https://a.test"),
            )
            create_source(
                connection,
                SourceRegistry(
                    source_name="Inactive",
                    source_type="website",
                    base_url="https://b.test",
                    is_active=False,
                ),
            )

            # C) Products
            create_product(
                connection,
                ProductProfile(product_name="P1", status="discovered", barcode="111"),
            )
            create_product(
                connection,
                ProductProfile(product_name="P2", status="draft", barcode="222"),
            )

            # D) Discovered URLs
            for url, status_value in [
                ("https://a.test/p/discovered", "discovered"),
                ("https://a.test/p/queued", "queued"),
                ("https://a.test/p/processed", "processed"),
                ("https://a.test/p/failed", "failed"),
            ]:
                create_discovered_url(
                    connection,
                    DiscoveredUrl(
                        source_id=source_active.source_id,
                        url=url,
                        discovery_type="sitemap",
                        status=status_value,
                    ),
                )

            # E) Jobs
            for job_id, status_value in [
                ("job-pending", JobStatus.pending),
                ("job-running", JobStatus.running),
                ("job-completed", JobStatus.completed),
                ("job-failed", JobStatus.failed),
            ]:
                create_discovery_job(
                    connection,
                    DiscoveryJob(
                        job_id=job_id,
                        job_type=JobType.url_extraction,
                        status=status_value,
                        priority=JobPriority.normal,
                        input_type="url",
                        input_value=f"https://jobs.test/{job_id}",
                    ),
                )

            # F) Latest extraction run
            older = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
            newer = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
            create_extraction_run(
                connection,
                ExtractionRun(
                    run_id="run-older",
                    source_id=source_active.source_id,
                    status="completed",
                    started_at=older,
                    completed_at=older,
                    pages_seen=12,
                    products_found=3,
                ),
            )
            create_extraction_run(
                connection,
                ExtractionRun(
                    run_id="run-newer",
                    source_id=source_active.source_id,
                    status="failed",
                    started_at=newer,
                    completed_at=newer,
                    pages_seen=20,
                    products_found=5,
                    error_message="network error",
                ),
            )

        response = client.get("/dashboard/summary")
        assert response.status_code == 200
        payload = response.json()

        assert payload["sources"]["total_sources"] == 2
        assert payload["sources"]["active_sources"] == 1
        assert payload["sources"]["inactive_sources"] == 1

        assert payload["products"]["total_products"] == 2
        assert payload["products"]["discovered_products"] == 1
        assert payload["products"]["products_today"] >= 2

        assert payload["urls"]["total_discovered_urls"] == 4
        assert payload["urls"]["queued_urls"] == 1
        assert payload["urls"]["processed_urls"] == 1
        assert payload["urls"]["failed_urls"] == 1
        assert payload["urls"]["discovered_urls_today"] >= 4

        assert payload["jobs"]["total_jobs"] == 4
        assert payload["jobs"]["pending_jobs"] == 1
        assert payload["jobs"]["running_jobs"] == 1
        assert payload["jobs"]["completed_jobs"] == 1
        assert payload["jobs"]["failed_jobs"] == 1
        assert payload["jobs"]["success_rate"] == 50.0

        assert payload["latest_run"]["run_id"] == "run-newer"
        assert payload["latest_run"]["pages_seen"] == 20
        assert payload["latest_run"]["products_found"] == 5

        for key in ["generated_at", "sources", "urls", "products", "jobs", "latest_run"]:
            assert key in payload
    finally:
        app.dependency_overrides.clear()
