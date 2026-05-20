import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

from app.discovery.sitemap import (
    build_sitemap_url,
    collect_sitemap_page_urls,
    fetch_sitemap_xml,
    filter_product_urls,
)
from app.extractors.product_page import extract_product_from_html, fetch_product_page_html
from app.scrapers.base import BaseSiteScraper, ScrapedProduct
from app.sources.models import SourceRegistry

_TITLE_SUFFIX_PATTERN = re.compile(
    r"\s*(?:\||-|–)?\s*(?:kim\s*geldi|kimgeldi(?:\.com)?)\s*$",
    re.IGNORECASE,
)
_PRICE_PATTERN = re.compile(
    r"(?:₺\s*(\d{1,3}(?:[.,]\d{3})*[.,]\d{2}|\d+[.,]\d{2})|(\d{1,3}(?:[.,]\d{3})*[.,]\d{2}|\d+[.,]\d{2})\s*TL)",
    re.IGNORECASE,
)
_BLOCKED_URL_TOKENS = ("/category", "/kategori", "/search", "/cart", "/blog")


class _KimgeldiHTMLFallbackParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.image_candidates: list[str] = []
        self._in_title = False
        self._in_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        tag_lower = tag.lower()
        if tag_lower == "meta":
            key = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
            content = attrs_dict.get("content", "").strip()
            if key in {"og:title", "og:image", "twitter:image"} and content:
                self.meta[key] = content
            return
        if tag_lower == "title":
            self._in_title = True
            return
        if tag_lower == "h1":
            self._in_h1 = True
            return
        if tag_lower == "img":
            src = attrs_dict.get("src", "").strip()
            if src:
                self.image_candidates.append(src)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._in_title = False
        elif tag_lower == "h1":
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        text = unescape(data).strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        if self._in_h1:
            self.h1_parts.append(text)


class KimgeldiScraper(BaseSiteScraper):
    domain_patterns = ["kimgeldi.com"]

    def __init__(self) -> None:
        self.errors: list[str] = []

    @staticmethod
    def _is_candidate_product_url(url: str) -> bool:
        lowered = url.lower()
        if any(token in lowered for token in _BLOCKED_URL_TOKENS):
            return False
        return "/urun" in lowered or "/product" in lowered

    def collect_product_urls(self, source: SourceRegistry, limit: int = 100) -> list[str]:
        sitemap_url = build_sitemap_url(source.base_url)
        page_urls, _ = collect_sitemap_page_urls(
            root_sitemap_url=sitemap_url,
            fetcher=fetch_sitemap_xml,
            max_sitemaps=10,
            max_urls=max(limit * 10, 200),
        )
        candidates = filter_product_urls(page_urls)

        unique: list[str] = []
        seen: set[str] = set()
        for url in candidates:
            if url in seen or not self._is_candidate_product_url(url):
                continue
            seen.add(url)
            unique.append(url)
            if len(unique) >= limit:
                break
        return unique

    @staticmethod
    def _clean_title(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = " ".join(unescape(value).split())
        cleaned = _TITLE_SUFFIX_PATTERN.sub("", cleaned).strip(" -|–")
        return cleaned or None

    @staticmethod
    def _parse_price(html_content: str) -> tuple[float | None, str | None]:
        match = _PRICE_PATTERN.search(html_content)
        if not match:
            return None, None
        raw_amount = (match.group(1) or match.group(2) or "").strip()
        normalized = raw_amount.replace(".", "").replace(",", ".")
        try:
            return float(normalized), "TRY"
        except ValueError:
            return None, None

    def _fallback_extract(self, source_url: str, html_content: str) -> ScrapedProduct | None:
        parser = _KimgeldiHTMLFallbackParser()
        parser.feed(html_content)

        name = self._clean_title(
            parser.meta.get("og:title")
            or (" ".join(parser.title_parts).strip() or None)
            or (" ".join(parser.h1_parts).strip() or None)
        )
        if not name:
            return None

        image_url = parser.meta.get("og:image") or parser.meta.get("twitter:image")
        if not image_url:
            for candidate in parser.image_candidates:
                candidate_lower = candidate.lower()
                if any(token in candidate_lower for token in ("logo", "icon", "sprite")):
                    continue
                image_url = candidate
                break

        price, currency = self._parse_price(html_content)
        if image_url is None and price is None:
            return None

        return ScrapedProduct(
            product_name=name,
            source_url=source_url,
            image_url=image_url,
            price=price,
            currency=currency,
            raw_data={"parser": "kimgeldi_fallback", "domain": urlparse(source_url).hostname},
        )

    def scrape(self, source: SourceRegistry, limit: int = 100) -> list[ScrapedProduct]:
        self.errors = []
        product_urls = self.collect_product_urls(source=source, limit=limit)
        scraped: list[ScrapedProduct] = []
        seen_urls: set[str] = set()
        seen_barcodes: set[str] = set()
        seen_names: set[str] = set()

        for url in product_urls:
            if len(scraped) >= limit or url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                html = fetch_product_page_html(url)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"{url}: {exc}")
                continue

            profile = extract_product_from_html(html, source_url=url)
            product: ScrapedProduct | None = None
            if profile and profile.product_name:
                image_url = profile.images[0].url if profile.images else None
                evidence_barcode = next(
                    (
                        ev.normalized_value
                        for ev in profile.evidence
                        if ev.field_name in {"barcode", "gtin"}
                    ),
                    None,
                )
                raw_price = next(
                    (ev.normalized_value for ev in profile.evidence if ev.field_name == "price"),
                    None,
                )
                price: float | None = None
                if raw_price:
                    try:
                        price = float(str(raw_price).replace(",", "."))
                    except ValueError:
                        price = None
                product = ScrapedProduct(
                    product_name=profile.product_name,
                    source_url=url,
                    image_url=image_url,
                    brand=profile.brand,
                    category=profile.category,
                    barcode=profile.barcode or evidence_barcode,
                    price=price,
                    currency="TRY" if price is not None else None,
                    raw_data={"status": profile.status, "extractor": "generic"},
                )
            else:
                product = self._fallback_extract(source_url=url, html_content=html)

            if product is None or not product.product_name:
                continue

            barcode_key = (product.barcode or "").strip()
            name_key = f"{urlparse(url).hostname}|{' '.join(product.product_name.lower().split())}"
            if barcode_key and barcode_key in seen_barcodes:
                continue
            if not barcode_key and name_key in seen_names:
                continue
            if barcode_key:
                seen_barcodes.add(barcode_key)
            else:
                seen_names.add(name_key)
            scraped.append(product)

        return scraped
