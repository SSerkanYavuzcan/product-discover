from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from app.discovery.sitemap import (
    SITEMAP_ACCEPT_HEADER,
    SITEMAP_USER_AGENT,
    SitemapDiscoveryError,
    build_sitemap_url,
    collect_sitemap_page_urls,
    discover_urls_from_source_sitemap,
    fetch_sitemap_xml,
    filter_product_urls,
    is_probable_product_url,
    parse_sitemap_urls,
)
from app.sources.models import SourceRegistry
from app.sources.repository import create_source
from app.storage import get_connection, initialize_database


def test_build_sitemap_url_handles_trailing_slash() -> None:
    assert build_sitemap_url("https://example.com") == "https://example.com/sitemap.xml"
    assert build_sitemap_url("https://example.com/") == "https://example.com/sitemap.xml"


def test_parse_sitemap_urls_supports_urlset_and_deduplicates() -> None:
    xml_content = """
    <urlset>
        <url><loc>https://example.com/product/a</loc></url>
        <url><loc>https://example.com/product/a</loc></url>
        <url><loc> https://example.com/product/b </loc></url>
    </urlset>
    """
    assert parse_sitemap_urls(xml_content) == [
        "https://example.com/product/a",
        "https://example.com/product/b",
    ]


def test_parse_sitemap_urls_supports_sitemap_index_and_namespaces() -> None:
    xml_content = """
    <sitemapindex xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
        <sitemap><loc>https://example.com/sitemap-products.xml</loc></sitemap>
        <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
    </sitemapindex>
    """
    assert parse_sitemap_urls(xml_content) == [
        "https://example.com/sitemap-products.xml",
        "https://example.com/sitemap-pages.xml",
    ]


def test_parse_sitemap_urls_raises_on_invalid_xml() -> None:
    with pytest.raises(SitemapDiscoveryError):
        parse_sitemap_urls("<urlset><url><loc>missing close")


def test_product_url_heuristics_and_filtering() -> None:
    product_url = "https://www.kimgeldi.com/jacobs-18-gr-3-u-1-arada-yumusak-icim"
    assert is_probable_product_url(product_url) is True

    assert is_probable_product_url("https://shop.example.com/kategori/kahve") is False
    assert is_probable_product_url("https://shop.example.com/search?q=coffee") is False
    assert is_probable_product_url("https://shop.example.com/cart") is False
    assert is_probable_product_url("https://shop.example.com/blog/some-post") is False

    urls = [
        "https://shop.example.com/kategori/kahve",
        "https://shop.example.com/jacobs-18-gr-3-u-1-arada-yumusak-icim",
        "https://shop.example.com/product/nescafe-3-u-1-arada-10-lu-extra",
        "https://shop.example.com/assets/logo.png",
    ]
    assert filter_product_urls(urls) == [
        "https://shop.example.com/jacobs-18-gr-3-u-1-arada-yumusak-icim",
        "https://shop.example.com/product/nescafe-3-u-1-arada-10-lu-extra",
    ]


def test_collect_sitemap_page_urls_recurses_indexes() -> None:
    pages, stats = collect_sitemap_page_urls(
        root_sitemap_url="https://example.com/sitemap.xml",
        fetcher=lambda url: {
            "https://example.com/sitemap.xml": """
                <sitemapindex>
                    <sitemap><loc>https://example.com/sitemap-a.xml</loc></sitemap>
                    <sitemap><loc>https://example.com/sitemap-b.xml</loc></sitemap>
                </sitemapindex>
            """,
            "https://example.com/sitemap-a.xml": """
                <urlset><url><loc>https://example.com/product/a</loc></url></urlset>
            """,
            "https://example.com/sitemap-b.xml": """
                <urlset><url><loc>https://example.com/product/b</loc></url></urlset>
            """,
        }[url],
    )

    assert set(pages) == {"https://example.com/product/a", "https://example.com/product/b"}
    assert stats["sitemaps_processed"] == 3
    assert stats["max_sitemaps_reached"] is False


def test_collect_sitemap_page_urls_respects_max_sitemaps() -> None:
    mapping = {
        "https://example.com/sitemap.xml": """
            <sitemapindex>
                <sitemap><loc>https://example.com/sitemap-1.xml</loc></sitemap>
                <sitemap><loc>https://example.com/sitemap-2.xml</loc></sitemap>
                <sitemap><loc>https://example.com/sitemap-3.xml</loc></sitemap>
            </sitemapindex>
        """,
        "https://example.com/sitemap-1.xml": "<urlset><url><loc>https://example.com/product/1</loc></url></urlset>",
        "https://example.com/sitemap-2.xml": "<urlset><url><loc>https://example.com/product/2</loc></url></urlset>",
        "https://example.com/sitemap-3.xml": "<urlset><url><loc>https://example.com/product/3</loc></url></urlset>",
    }
    pages, stats = collect_sitemap_page_urls("https://example.com/sitemap.xml", fetcher=lambda url: mapping[url], max_sitemaps=2)

    assert len(pages) == 1
    assert stats["sitemaps_processed"] == 2
    assert stats["max_sitemaps_reached"] is True


def test_fetch_sitemap_xml_uses_headers_and_decodes() -> None:
    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b"<urlset></urlset>"

    captured_request = {}

    def fake_urlopen(request, timeout):
        captured_request["request"] = request
        captured_request["timeout"] = timeout
        return DummyResponse()

    with patch("app.discovery.sitemap.urlopen", side_effect=fake_urlopen):
        xml = fetch_sitemap_xml("https://example.com/sitemap.xml", timeout_seconds=3.0)

    request = captured_request["request"]
    assert request.headers["User-agent"] == SITEMAP_USER_AGENT
    assert request.headers["Accept"] == SITEMAP_ACCEPT_HEADER
    assert captured_request["timeout"] == 3.0
    assert xml == "<urlset></urlset>"


def test_fetch_sitemap_xml_errors() -> None:
    with patch("app.discovery.sitemap.urlopen", side_effect=HTTPError("u", 500, "bad", {}, None)):
        with pytest.raises(SitemapDiscoveryError):
            fetch_sitemap_xml("https://example.com/sitemap.xml")

    with patch("app.discovery.sitemap.urlopen", side_effect=URLError("down")):
        with pytest.raises(SitemapDiscoveryError):
            fetch_sitemap_xml("https://example.com/sitemap.xml")

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b""

    with patch("app.discovery.sitemap.urlopen", return_value=EmptyResponse()):
        with pytest.raises(SitemapDiscoveryError):
            fetch_sitemap_xml("https://example.com/sitemap.xml")


def test_discover_urls_from_source_sitemap_persists_and_completes(tmp_path: Path) -> None:
    db_path = tmp_path / "sitemap.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        source = create_source(
            connection,
            SourceRegistry(
                source_name="Demo",
                source_type="retailer",
                base_url="https://example.com",
            ),
        )

        def fake_fetcher(url: str) -> str:
            if url == "https://example.com/sitemap.xml":
                return """
                <sitemapindex>
                    <sitemap><loc>https://example.com/sitemap-products.xml</loc></sitemap>
                    <sitemap><loc>https://example.com/sitemap-products.xml</loc></sitemap>
                </sitemapindex>
                """
            if url == "https://example.com/sitemap-products.xml":
                return """
                <urlset>
                    <url><loc>https://example.com/product/widget-1</loc></url>
                    <url><loc>https://example.com/category/widgets</loc></url>
                    <url><loc>https://example.com/product/widget-1</loc></url>
                </urlset>
                """
            raise SitemapDiscoveryError("unexpected")

        run = discover_urls_from_source_sitemap(
            connection, source.source_id, fetcher=fake_fetcher
        )

        assert run is not None
        assert run.status == "completed"
        assert run.pages_seen == 2
        assert run.products_found == 1
        assert run.completed_at is not None

        discovered = connection.execute(
            "SELECT url, discovery_type, status FROM discovered_urls ORDER BY url"
        ).fetchall()
        assert len(discovered) == 1
        assert discovered[0]["url"] == "https://example.com/product/widget-1"
        assert discovered[0]["discovery_type"] == "sitemap"
        assert discovered[0]["status"] == "discovered"


def test_discover_urls_from_source_sitemap_missing_source_returns_none(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "missing.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        assert discover_urls_from_source_sitemap(connection, "unknown") is None


def test_discover_urls_from_source_sitemap_marks_failed(tmp_path: Path) -> None:
    db_path = tmp_path / "failed.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        source = create_source(
            connection,
            SourceRegistry(
                source_name="Demo",
                source_type="retailer",
                base_url="https://example.com",
            ),
        )

        def failing_fetcher(url: str) -> str:
            raise SitemapDiscoveryError("boom")

        run = discover_urls_from_source_sitemap(
            connection,
            source.source_id,
            fetcher=failing_fetcher,
        )
        assert run is not None
        assert run.status == "failed"
        assert run.error_message == "boom"
        assert run.completed_at is not None


def test_discover_urls_from_source_sitemap_supports_more_than_five_child_sitemaps(tmp_path: Path) -> None:
    db_path = tmp_path / "more_children.db"
    initialize_database(str(db_path))

    with get_connection(str(db_path)) as connection:
        source = create_source(
            connection,
            SourceRegistry(source_name="Many", source_type="retailer", base_url="https://example.com"),
        )

        children = "".join(
            f"<sitemap><loc>https://example.com/sitemap-{idx}.xml</loc></sitemap>" for idx in range(1, 8)
        )

        def fake_fetcher(url: str) -> str:
            if url == "https://example.com/sitemap.xml":
                return f"<sitemapindex>{children}</sitemapindex>"
            if "sitemap-" in url:
                idx = url.split("-")[-1].split(".")[0]
                return f"<urlset><url><loc>https://example.com/product/item-{idx}</loc></url></urlset>"
            raise SitemapDiscoveryError("unexpected")

        run = discover_urls_from_source_sitemap(
            connection, source.source_id, fetcher=fake_fetcher, max_child_sitemaps=10
        )

        assert run is not None
        assert run.pages_seen == 7
        assert run.products_found == 7
