import json
from urllib.error import HTTPError, URLError

import pytest

from app.extractors.product_page import (
    PRODUCT_PAGE_ACCEPT_HEADER,
    PRODUCT_PAGE_USER_AGENT,
    ProductPageFetchError,
    extract_json_ld_products,
    extract_product_from_html,
    extract_product_from_url,
    fetch_product_page_html,
)


class _MockResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload.encode("utf-8")

    def __enter__(self) -> "_MockResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_extract_json_ld_products_from_single_dict() -> None:
    products = extract_json_ld_products([json.dumps({"@type": "Product", "name": "A"})])
    assert len(products) == 1
    assert products[0]["name"] == "A"


def test_extract_json_ld_products_from_list() -> None:
    block = json.dumps([{"@type": "Thing"}, {"@type": "Product", "name": "B"}])
    products = extract_json_ld_products([block])
    assert len(products) == 1
    assert products[0]["name"] == "B"


def test_extract_json_ld_products_from_graph() -> None:
    block = json.dumps({"@graph": [{"@type": "Product", "name": "C"}]})
    products = extract_json_ld_products([block])
    assert len(products) == 1
    assert products[0]["name"] == "C"


def test_extract_json_ld_products_ignores_invalid_json() -> None:
    products = extract_json_ld_products(["not-json"])
    assert products == []


def test_extract_product_from_html_prefers_json_ld() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","name":"Product A","description":"Great",
    "brand":{"name":"Brand A"},"category":"Snacks","image":"https://example.com/a.jpg"}
    </script>
    </head><body></body></html>
    """
    profile = extract_product_from_html(html, "https://example.com/p")
    assert profile is not None
    assert profile.product_name == "Product A"
    assert profile.brand == "Brand A"
    assert profile.description == "Great"
    assert profile.category == "Snacks"
    assert profile.images and profile.images[0].url == "https://example.com/a.jpg"


def test_extract_product_from_html_falls_back_to_open_graph() -> None:
    html = """
    <html><head>
    <meta property="product:price:amount" content="10.00" />
    <meta property="og:title" content="OG Product" />
    <meta property="og:description" content="OG Desc" />
    <meta property="og:image" content="https://example.com/og.jpg" />
    </head><body></body></html>
    """
    profile = extract_product_from_html(html, "https://example.com/p")
    assert profile is not None
    assert profile.product_name == "OG Product"
    assert profile.description == "OG Desc"
    assert profile.images and profile.images[0].url == "https://example.com/og.jpg"


def test_extract_product_from_html_falls_back_to_title_and_meta_description() -> None:
    html = """
    <html><head>
    <meta property="product:brand" content="Generic Brand" />
    <title>Title Product</title>
    <meta name="description" content="Meta Desc" />
    <meta property="og:image" content="https://example.com/meta.jpg" />
    </head><body></body></html>
    """
    profile = extract_product_from_html(html, "https://example.com/p")
    assert profile is not None
    assert profile.product_name == "Title Product"
    assert profile.description == "Meta Desc"


def test_extract_product_from_html_uses_product_like_url_fallback_without_structured_data() -> None:
    html = """
    <html><head>
    <meta property="og:title" content="Jacobs 18 Gr 3 Ü 1 Arada Yumuşak İçim | Kim Geldi" />
    <meta property="og:description" content="Kahve ürünü" />
    <meta property="og:image" content="https://example.com/jacobs.jpg" />
    </head><body></body></html>
    """
    profile = extract_product_from_html(
        html,
        "https://www.kimgeldi.com/jacobs-18-gr-3-u-1-arada-yumusak-icim",
    )

    assert profile is not None
    assert profile.product_name == "Jacobs 18 Gr 3 Ü 1 Arada Yumuşak İçim"
    assert profile.images and profile.images[0].url == "https://example.com/jacobs.jpg"
    assert profile.confidence is not None
    assert profile.confidence.field_scores["product_name"] == 0.6


def test_extract_product_from_html_rejects_non_product_url_fallback() -> None:
    html = """
    <html><head>
    <meta property="og:title" content="Coffee Category | Store" />
    <meta property="og:image" content="https://example.com/category.jpg" />
    </head><body></body></html>
    """

    assert extract_product_from_html(html, "https://example.com/category/coffee-products") is None
    assert extract_product_from_html(html, "https://example.com/cart") is None


def test_extract_product_from_html_sets_barcode_and_gtin_when_hint_found() -> None:
    html = """
    <html><head>
    <meta property="product:price:amount" content="25.00" />
    <title>Product</title>
    <meta property="og:image" content="https://example.com/barcode.jpg" />
    </head>
    <body>Barcode: 3017620422003</body></html>
    """
    profile = extract_product_from_html(html, "https://example.com/p", barcode_hint="3017620422003")
    assert profile is not None
    assert profile.barcode == "3017620422003"
    assert profile.gtin == "3017620422003"


def test_extract_product_from_html_returns_none_without_useful_signal() -> None:
    html = "<html><head></head><body>nothing useful</body></html>"
    assert extract_product_from_html(html, "https://example.com/p") is None


def test_extracted_profile_includes_evidence_and_confidence_range() -> None:
    html = """
    <html><head>
    <meta property="product:price:currency" content="TRY" />
    <meta property="og:title" content="OG Product" />
    <meta property="og:image" content="https://example.com/evidence.jpg" />
    </head><body></body></html>
    """
    profile = extract_product_from_html(html, "https://example.com/p")
    assert profile is not None
    assert profile.evidence
    assert profile.confidence is not None
    assert 0 <= profile.confidence.overall <= 1


def test_fetch_product_page_html_sends_expected_headers(monkeypatch) -> None:
    captured = {}

    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        captured["request"] = request
        return _MockResponse("<html></html>")

    monkeypatch.setattr("app.extractors.product_page.urlopen", mock_urlopen)
    html = fetch_product_page_html("https://example.com/p")

    assert html == "<html></html>"
    request = captured["request"]
    assert request.headers.get("User-agent") == PRODUCT_PAGE_USER_AGENT
    assert request.headers.get("Accept") == PRODUCT_PAGE_ACCEPT_HEADER


def test_fetch_product_page_html_returns_html_with_mocked_urlopen(monkeypatch) -> None:
    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        return _MockResponse("<html><body>ok</body></html>")

    monkeypatch.setattr("app.extractors.product_page.urlopen", mock_urlopen)
    assert "ok" in fetch_product_page_html("https://example.com/p")


def test_fetch_product_page_html_raises_on_http_error(monkeypatch) -> None:
    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        raise HTTPError("https://example.com", 500, "boom", None, None)

    monkeypatch.setattr("app.extractors.product_page.urlopen", mock_urlopen)
    with pytest.raises(ProductPageFetchError, match="HTTP error"):
        fetch_product_page_html("https://example.com/p")


def test_fetch_product_page_html_raises_on_url_error(monkeypatch) -> None:
    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        raise URLError("down")

    monkeypatch.setattr("app.extractors.product_page.urlopen", mock_urlopen)
    with pytest.raises(ProductPageFetchError, match="network error"):
        fetch_product_page_html("https://example.com/p")


def test_extract_product_from_url_calls_fetch_and_parse(monkeypatch) -> None:
    html = """
    <html><head>
    <meta property="product:condition" content="new" />
    <meta property="og:title" content="From URL" />
    <meta property="og:image" content="https://example.com/url.jpg" />
    </head><body></body></html>
    """

    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        return _MockResponse(html)

    monkeypatch.setattr("app.extractors.product_page.urlopen", mock_urlopen)

    profile = extract_product_from_url("https://example.com/p")
    assert profile is not None
    assert profile.product_name == "From URL"
