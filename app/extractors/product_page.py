import json
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.models import ConfidenceScore, ProductImage, ProductProfile, SourceEvidence

PRODUCT_PAGE_USER_AGENT = (
    "ProductDiscoverAgent/0.1 (https://github.com/SSerkanYavuzcan/product-discover)"
)
PRODUCT_PAGE_ACCEPT_HEADER = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


class ProductPageFetchError(RuntimeError):
    pass


class _ProductPageHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.json_ld_blocks: list[str] = []
        self.body_text_parts: list[str] = []

        self._in_title = False
        self._in_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        tag_lower = tag.lower()

        if tag_lower == "title":
            self._in_title = True
            return

        if tag_lower == "meta":
            key = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
            content = attrs_dict.get("content", "").strip()
            
            # product: ile başlayan tüm e-ticaret meta etiketlerini yakala
            if (key.startswith("product:") or key in {
                "description",
                "og:title",
                "og:description",
                "og:image",
            }) and content:
                self.meta[key] = content
            return

        if tag_lower == "script" and attrs_dict.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._json_ld_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._in_title = False
            return

        if tag_lower == "script" and self._in_json_ld:
            block = "".join(self._json_ld_parts).strip()
            if block:
                self.json_ld_blocks.append(block)
            self._in_json_ld = False
            self._json_ld_parts = []

    def handle_data(self, data: str) -> None:
        text = unescape(data).strip()
        if not text:
            return

        if self._in_title:
            self.title_parts.append(text)
        if self._in_json_ld:
            self._json_ld_parts.append(data)
        self.body_text_parts.append(text)


def fetch_product_page_html(url: str, timeout_seconds: float = 10.0) -> str:
    request = Request(
        url=url,
        headers={
            "User-Agent": PRODUCT_PAGE_USER_AGENT,
            "Accept": PRODUCT_PAGE_ACCEPT_HEADER,
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            content = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise ProductPageFetchError(f"Product page HTTP error: {exc.code}") from exc
    except URLError as exc:
        raise ProductPageFetchError(f"Product page network error: {exc.reason}") from exc
    except OSError as exc:
        raise ProductPageFetchError(f"Product page fetch failed: {exc}") from exc

    if not content.strip():
        raise ProductPageFetchError("Product page response was empty")

    return content


def _normalize_product_type(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() == "product"
    if isinstance(value, list):
        return any(isinstance(item, str) and item.lower() == "product" for item in value)
    return False


def extract_json_ld_products(json_ld_blocks: list[str]) -> list[dict]:
    products: list[dict] = []

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            if _normalize_product_type(node.get("@type")):
                products.append(node)
            graph = node.get("@graph")
            if isinstance(graph, list):
                for child in graph:
                    collect(child)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    for block in json_ld_blocks:
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        collect(payload)

    return products


def _source_name_from_url(source_url: str) -> str:
    hostname = urlparse(source_url).hostname
    return hostname if hostname else "Product page"


def _extract_brand(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        brand_name = value.get("name")
        return brand_name if isinstance(brand_name, str) else None
    return None


def _extract_image(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                return item
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                return item["url"]
    if isinstance(value, dict) and isinstance(value.get("url"), str):
        return value["url"]
    return None


def extract_product_from_html(
    html_content: str,
    source_url: str,
    barcode_hint: str | None = None,
) -> ProductProfile | None:
    parser = _ProductPageHTMLParser()
    parser.feed(html_content)

    title = " ".join(parser.title_parts).strip() or None
    meta = parser.meta
    page_text = " ".join(parser.body_text_parts)

    json_ld_products = extract_json_ld_products(parser.json_ld_blocks)
    json_ld_product = json_ld_products[0] if json_ld_products else None

    name: str | None = None
    description: str | None = None
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None

    evidence: list[SourceEvidence] = []
    field_scores: dict[str, float] = {}

    now = datetime.now(UTC)
    source_name = _source_name_from_url(source_url)

    def add_evidence(field: str, raw_value: Any, normalized: Any, confidence: float) -> None:
        evidence.append(
            SourceEvidence(
                source_name=source_name,
                source_type="product_page",
                source_url=source_url,
                field_name=field,
                raw_value=None if raw_value is None else str(raw_value),
                normalized_value=None if normalized is None else str(normalized),
                confidence=confidence,
                extracted_at=now,
            )
        )
        field_scores[field] = confidence

    if json_ld_product is not None:
        name = json_ld_product.get("name") if isinstance(json_ld_product.get("name"), str) else None
        description = (
            json_ld_product.get("description")
            if isinstance(json_ld_product.get("description"), str)
            else None
        )
        brand = _extract_brand(json_ld_product.get("brand"))
        category = (
            json_ld_product.get("category")
            if isinstance(json_ld_product.get("category"), str)
            else None
        )
        image_url = _extract_image(json_ld_product.get("image"))

    if name is None:
        name = meta.get("og:title") or title
    if description is None:
        description = meta.get("og:description") or meta.get("description")
    if brand is None:
        brand = meta.get("product:brand")
    if category is None:
        category = meta.get("product:category")
    if image_url is None:
        image_url = meta.get("og:image")

    # --- KATI DOĞRULAMA (STRICT VALIDATION) EKLENDİ ---
    # Gerçek bir ürün sayfası olup olmadığını kontrol et
    is_explicit_product = False
    
    # 1. JSON-LD içinde @type: Product var mı?
    if json_ld_product is not None:
        is_explicit_product = True
    # 2. Meta etiketlerinde product: verileri var mı? (Örn: product:price:amount)
    elif any(k.startswith("product:") for k in meta.keys()):
        is_explicit_product = True

    # Eğer e-ticaret datası yoksa veya ürünün ismi/resmi yoksa atla (None dön)
    if not is_explicit_product or not name or not image_url:
        return None

    if name:
        add_evidence("product_name", name, name, 0.85 if json_ld_product else 0.65)
    if description:
        add_evidence(
            "description",
            description,
            description,
            0.75 if json_ld_product and json_ld_product.get("description") else 0.6,
        )
    if brand:
        add_evidence(
            "brand",
            brand,
            brand,
            0.75 if json_ld_product and _extract_brand(json_ld_product.get("brand")) else 0.6,
        )
    if category:
        add_evidence(
            "category",
            category,
            category,
            0.75 if json_ld_product and isinstance(json_ld_product.get("category"), str) else 0.6,
        )
    if image_url:
        add_evidence(
            "image",
            image_url,
            image_url,
            0.75 if json_ld_product and _extract_image(json_ld_product.get("image")) else 0.6,
        )

    barcode: str | None = None
    gtin: str | None = None
    if barcode_hint:
        barcode_text_match = barcode_hint in page_text
        json_ld_text = json.dumps(json_ld_product) if json_ld_product is not None else ""
        barcode_json_match = barcode_hint in json_ld_text

        barcode_fields = ["gtin", "gtin8", "gtin12", "gtin13", "gtin14", "sku"]
        explicit_match = False
        if json_ld_product is not None:
            for field in barcode_fields:
                value = json_ld_product.get(field)
                if isinstance(value, str) and value == barcode_hint:
                    explicit_match = True
                    break

        if barcode_text_match or barcode_json_match or explicit_match:
            barcode = barcode_hint
            gtin = barcode_hint
            add_evidence("barcode", barcode_hint, barcode_hint, 0.9)

    if not evidence:
        return None

    overall = round(sum(field_scores.values()) / len(field_scores), 3)

    images = (
        [
            ProductImage(
                url=image_url,
                image_type="main",
                source_url=source_url,
                confidence=0.75,
            )
        ]
        if image_url
        else []
    )

    return ProductProfile(
        barcode=barcode,
        gtin=gtin,
        product_name=name,
        brand=brand,
        category=category,
        description=description,
        images=images,
        evidence=evidence,
        confidence=ConfidenceScore(overall=overall, field_scores=field_scores),
        status="discovered",
    )


def extract_product_from_url(
    url: str,
    barcode_hint: str | None = None,
    timeout_seconds: float = 10.0,
) -> ProductProfile | None:
    html_content = fetch_product_page_html(url=url, timeout_seconds=timeout_seconds)
    return extract_product_from_html(
        html_content=html_content,
        source_url=url,
        barcode_hint=barcode_hint,
    )
