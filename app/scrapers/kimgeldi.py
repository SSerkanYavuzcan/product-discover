from app.discovery.sitemap import (
    build_sitemap_url,
    collect_sitemap_page_urls,
    fetch_sitemap_xml,
    filter_product_urls,
)
from app.extractors.product_page import extract_product_from_url
from app.scrapers.base import BaseSiteScraper, ScrapedProduct
from app.sources.models import SourceRegistry


class KimgeldiScraper(BaseSiteScraper):
    domain_patterns = ["kimgeldi.com"]

    def scrape(self, source: SourceRegistry, limit: int = 100) -> list[ScrapedProduct]:
        sitemap_url = build_sitemap_url(source.base_url)
        page_urls, _ = collect_sitemap_page_urls(
            root_sitemap_url=sitemap_url,
            fetcher=fetch_sitemap_xml,
            max_sitemaps=5,
        )
        candidate_urls = filter_product_urls(page_urls)

        scraped: list[ScrapedProduct] = []
        for url in candidate_urls:
            if len(scraped) >= limit:
                break
            product = extract_product_from_url(url)
            if product is None or not product.product_name:
                continue
            scraped.append(
                ScrapedProduct(
                    product_name=product.product_name,
                    source_url=url,
                    image_url=product.images[0].url if product.images else None,
                    brand=product.brand,
                    category=product.category,
                    barcode=product.barcode,
                    raw_data={"status": product.status},
                )
            )
        return scraped
