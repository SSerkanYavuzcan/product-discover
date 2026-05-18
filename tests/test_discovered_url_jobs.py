from app.jobs.repository import get_discovery_job
from app.processing.discovered_url_jobs import create_url_extraction_jobs_from_discovered_urls
from app.sources import create_discovered_url, create_source
from app.sources.models import DiscoveredUrl, SourceRegistry
from app.storage.database import get_connection, initialize_database


def test_create_url_extraction_jobs_from_discovered_urls_passes_source_id(tmp_path) -> None:
    db_path = tmp_path / "discovered_url_jobs.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        source = create_source(
            connection,
            SourceRegistry(source_name="Source", source_type="website", base_url="https://a.com"),
        )
        create_discovered_url(
            connection,
            DiscoveredUrl(
                source_id=source.source_id,
                url="https://a.com/p/1",
                discovery_type="sitemap",
                status="discovered",
            ),
        )

        result = create_url_extraction_jobs_from_discovered_urls(
            connection=connection,
            source_id=source.source_id or "",
        )
        assert result is not None
        job = get_discovery_job(connection, result.job_ids[0])

    assert job is not None
    assert job.source_id == source.source_id
