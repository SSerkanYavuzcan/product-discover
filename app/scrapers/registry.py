from app.scrapers.base import BaseSiteScraper
from app.scrapers.kimgeldi import KimgeldiScraper
from app.sources.models import SourceRegistry

REGISTERED_SCRAPERS: list[BaseSiteScraper] = [KimgeldiScraper()]


def get_scraper_for_source(source: SourceRegistry) -> BaseSiteScraper | None:
    for scraper in REGISTERED_SCRAPERS:
        if scraper.can_handle(source.base_url):
            return scraper
    return None
