import sqlite3
from collections.abc import Callable
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
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


def product_url_score(url: str) -> tuple[int, list[str]]:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()
    reasons: list[str] = []

    static_extensions = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".css", ".js", ".pdf")
    if path.endswith(static_extensions):
        return -100, ["static_extension"]

    blocked_patterns = (
        "/cart", "/basket", "/checkout", "/login", "/register", "/account",
        "/search", "/category", "/categories", "/kategori", "/kategoriler",
        "/blog", "/contact", "/about", "/brand", "/marka",
        "/campaign", "/kampanya", "/page", "/sayfa", "/policies",
    )
    if any(pattern in path for pattern in blocked_patterns):
        return -100, ["blocked_path"]

    if "search" in parse_qs(query):
        return -100, ["search_query"]

    score = 0
    product_patterns = (
        "/product", "/products", "/urun", "/urunler",
        "/p/", "-p-", "-u-", ".html", "product-detail",
    )
    if any(pattern in path for pattern in product_patterns):
        score += 3
        reasons.append("explicit_product_pattern")

    segments = [segment for segment in path.split("/") if segment]
    last_segment = segments[-1] if segments else ""
    slug_tokens = [token for token in last_segment.split("-") if token]

    if len(last_segment) >= 20:
        score += 2
        reasons.append("long_slug")

    if len(slug_tokens) >= 3:
        score += 1
        reasons.append("hyphenated_slug")

    if any(any(ch.isdigit() for ch in token) for token in slug_tokens):
        score += 1
        reasons.append("numeric_token")

    quantity_tokens = {"gr", "kg", "ml", "lt", "l", "adet", "li", "lu", "paket", "pk", "x"}
    if any(token in quantity_tokens for token in slug_tokens):
        score += 1
        reasons.append("quantity_token")

    return score, reasons


def is_probable_product_url(url: str) -> bool:
    score, _ = product_url_score(url)
    return score >= 3


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




def collect_sitemap_page_urls(
    root_sitemap_url: str,
    fetcher: Callable[[str], str],
    max_sitemaps: int = 100,
    max_urls: int = 50000,
) -> tuple[list[str], dict[str, int | bool]]:
    pending = [root_sitemap_url]
    seen_sitemaps: set[str] = set()
    seen_pages: set[str] = set()

    sitemaps_processed = 0
    pages_seen = 0
    max_sitemaps_reached = False
    max_urls_reached = False

    while pending:
        sitemap_url = pending.pop(0)
        if sitemap_url in seen_sitemaps:
            continue

        if sitemaps_processed >= max_sitemaps:
            max_sitemaps_reached = True
            break

        seen_sitemaps.add(sitemap_url)
        sitemap_urls = parse_sitemap_urls(fetcher(sitemap_url))
        sitemaps_processed += 1

        for discovered_url in sitemap_urls:
            if _looks_like_sitemap_url(discovered_url):
                if discovered_url not in seen_sitemaps:
                    pending.append(discovered_url)
                continue

            pages_seen += 1
            if discovered_url in seen_pages:
                continue
            seen_pages.add(discovered_url)

            if len(seen_pages) >= max_urls:
                max_urls_reached = True
                break

        if max_urls_reached:
            break

    stats: dict[str, int | bool] = {
        "sitemaps_seen": len(seen_sitemaps) + len({u for u in pending if u not in seen_sitemaps}),
        "sitemaps_processed": sitemaps_processed,
        "pages_seen": pages_seen,
        "max_sitemaps_reached": max_sitemaps_reached,
        "max_urls_reached": max_urls_reached,
    }
    return list(seen_pages), stats

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
        page_urls, stats = collect_sitemap_page_urls(
            root_sitemap_url=root_sitemap_url,
            fetcher=fetcher,
            max_sitemaps=max_child_sitemaps,
        )

        pages_seen = int(stats["pages_seen"])
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
            error_message=(
                f"Sitemap stats: processed={stats['sitemaps_processed']}, "
                f"seen={stats['sitemaps_seen']}, pages_seen={stats['pages_seen']}, "
                f"product_candidates={len(candidate_urls)}, "
                f"max_sitemaps_reached={stats['max_sitemaps_reached']}, "
                f"max_urls_reached={stats['max_urls_reached']}"
            ),
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
