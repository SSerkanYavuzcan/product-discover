import sqlite3
from collections.abc import Callable
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from app.sources.models import DiscoveredUrl, ExtractionRun
from app.sources.repository import (
    create_discovered_url,
    create_extraction_run,
    get_source,
    update_extraction_run_status,
)

SITEMAP_USER_AGENT = "ProductDiscoverAgent/0.1 (https://github.com/SSerkanYavuzcan/product-discover)"
SITEMAP_ACCEPT_HEADER = "application/xml,text/xml,*/*;q=0.8"


class SitemapDiscoveryError(RuntimeError):
    pass


def build_sitemap_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return f"{normalized}/sitemap.xml"


def fetch_sitemap_xml(url: str, timeout_seconds: float = 10.0) -> str:
    request = Request(
        url,
        headers={"User-Agent": SITEMAP_USER_AGENT, "Accept": SITEMAP_ACCEPT_HEADER},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except (HTTPError, URLError, OSError) as exc:
        raise SitemapDiscoveryError(f"Failed to fetch sitemap at {url}: {exc}") from exc

    if not payload:
        raise SitemapDiscoveryError(f"Empty sitemap response from {url}")

    return payload.decode("utf-8", errors="replace")


def _local_name(tag_name: str) -> str:
    return tag_name.rsplit("}", 1)[-1]


def parse_sitemap_urls(xml_content: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml_content)
    except ElementTree.ParseError as exc:
        raise SitemapDiscoveryError(f"Invalid sitemap XML: {exc}") from exc

    urls: list[str] = []
    seen: set[str] = set()

    for node in root.iter():
        if _local_name(node.tag) != "loc":
            continue
        value = (node.text or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        urls.append(value)

    return urls


def is_probable_product_url(url: str) -> bool:
    path = urlparse(url).path.lower()

    static_extensions = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".css", ".js", ".pdf")
    if path.endswith(static_extensions):
        return False

    blocked_patterns = (
        "/cart",
        "/basket",
        "/checkout",
        "/login",
        "/register",
        "/account",
        "/contact",
        "/about",
        "/blog",
        "/category",
        "/categories",
        "/search",
    )
    if any(pattern in path for pattern in blocked_patterns):
        return False

    product_patterns = (
        "/product",
        "/products",
        "/urun",
        "/urunler",
        "/p/",
        "-p-",
        "product-detail",
        "productdetails",
    )
    if any(pattern in path for pattern in product_patterns):
        return True

    segments = [segment for segment in path.split("/") if segment]
    return len(segments) >= 2


def filter_product_urls(urls: list[str]) -> list[str]:
    filtered: list[str] = []
    seen: set[str] = set()

    for url in urls:
        if url in seen or not is_probable_product_url(url):
            continue
        seen.add(url)
        filtered.append(url)

    return filtered


def _looks_like_sitemap_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".xml") or "sitemap" in path


def discover_urls_from_source_sitemap(
    connection: sqlite3.Connection,
    source_id: str,
    fetcher: Callable[[str], str] = fetch_sitemap_xml,
    max_child_sitemaps: int = 5,
    product_only: bool = True,
) -> ExtractionRun | None:
    source = get_source(connection, source_id)
    if source is None:
        return None

    run = create_extraction_run(
        connection,
        ExtractionRun(source_id=source_id, status="running", pages_seen=0, products_found=0),
    )

    try:
        root_sitemap_url = build_sitemap_url(source.base_url)
        root_urls = parse_sitemap_urls(fetcher(root_sitemap_url))

        child_sitemaps = [url for url in root_urls if _looks_like_sitemap_url(url)]
        page_urls = [url for url in root_urls if not _looks_like_sitemap_url(url)]

        if child_sitemaps:
            for child_url in child_sitemaps[:max_child_sitemaps]:
                child_urls = parse_sitemap_urls(fetcher(child_url))
                page_urls.extend([url for url in child_urls if not _looks_like_sitemap_url(url)])

        pages_seen = len(page_urls)
        candidate_urls = (
            filter_product_urls(page_urls)
            if product_only
            else list(dict.fromkeys(page_urls))
        )

        persisted = 0
        for url in candidate_urls:
            try:
                create_discovered_url(
                    connection,
                    DiscoveredUrl(
                        source_id=source_id,
                        url=url,
                        discovery_type="sitemap",
                        status="discovered",
                    ),
                )
                persisted += 1
            except sqlite3.IntegrityError:
                continue

        updated = update_extraction_run_status(
            connection,
            cast(str, run.run_id),
            status="completed",
            pages_seen=pages_seen,
            products_found=persisted,
            mark_completed=True,
        )
        return updated
    except SitemapDiscoveryError as exc:
        return update_extraction_run_status(
            connection,
            cast(str, run.run_id),
            status="failed",
            error_message=str(exc),
            mark_completed=True,
        )
