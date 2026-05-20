from app.scrapers.kimgeldi import KimgeldiScraper
from app.sources.models import SourceRegistry


def test_collect_product_urls_dedup_and_filters(monkeypatch) -> None:
    scraper = KimgeldiScraper()
    source = SourceRegistry(source_name="K", source_type="website", base_url="https://kimgeldi.com")

    monkeypatch.setattr(
        "app.scrapers.kimgeldi.collect_sitemap_page_urls",
        lambda **kwargs: ([
            "https://kimgeldi.com/urun/ornek-urun-1",
            "https://kimgeldi.com/urun/ornek-urun-1",
            "https://kimgeldi.com/category/atistirmalik",
            "https://kimgeldi.com/blog/yazi",
            "https://kimgeldi.com/urun/ornek-urun-2",
        ], {}),
    )
    monkeypatch.setattr("app.scrapers.kimgeldi.filter_product_urls", lambda urls: urls)

    urls = scraper.collect_product_urls(source, limit=10)
    assert urls == [
        "https://kimgeldi.com/urun/ornek-urun-1",
        "https://kimgeldi.com/urun/ornek-urun-2",
    ]


def test_fallback_extracts_name_and_image() -> None:
    scraper = KimgeldiScraper()
    html = """
    <html><head>
      <meta property='og:title' content='Demo Ürün | Kim Geldi'>
      <meta property='og:image' content='https://cdn.example.com/demo.jpg'>
    </head><body></body></html>
    """
    item = scraper._fallback_extract("https://kimgeldi.com/urun/demo", html)
    assert item is not None
    assert item.product_name == "Demo Ürün"
    assert item.image_url == "https://cdn.example.com/demo.jpg"


def test_fallback_extracts_try_price_with_comma() -> None:
    scraper = KimgeldiScraper()
    html = """
    <html><head>
      <meta property='og:title' content='Fiyatlı Ürün - Kimgeldi'>
    </head><body>Satış Fiyatı: ₺123,45</body></html>
    """
    item = scraper._fallback_extract("https://kimgeldi.com/urun/fiyatli", html)
    assert item is not None
    assert item.product_name == "Fiyatlı Ürün"
    assert item.price == 123.45
    assert item.currency == "TRY"


def test_rejects_non_product_urls() -> None:
    scraper = KimgeldiScraper()
    assert scraper._is_candidate_product_url("https://kimgeldi.com/cart") is False
    assert scraper._is_candidate_product_url("https://kimgeldi.com/search?q=cips") is False
    assert scraper._is_candidate_product_url("https://kimgeldi.com/blog/yazi") is False
    assert scraper._is_candidate_product_url("https://kimgeldi.com/urun/demo") is True
