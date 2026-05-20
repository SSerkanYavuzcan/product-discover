from app.scrapers.kimgeldi import KimgeldiScraper
from app.scrapers.registry import get_scraper_for_source
from app.sources.models import SourceRegistry


def test_registry_returns_kimgeldi_scraper_for_kimgeldi_domain() -> None:
    source = SourceRegistry(
        source_name="Kimgeldi",
        source_type="website",
        base_url="https://www.kimgeldi.com",
    )
    scraper = get_scraper_for_source(source)
    assert isinstance(scraper, KimgeldiScraper)


def test_registry_returns_none_for_unknown_domain() -> None:
    source = SourceRegistry(
        source_name="Unknown",
        source_type="website",
        base_url="https://example.org",
    )
    scraper = get_scraper_for_source(source)
    assert scraper is None
