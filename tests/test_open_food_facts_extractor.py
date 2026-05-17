import json
from urllib.error import HTTPError, URLError

import pytest

from app.extractors.open_food_facts import (
    OPEN_FOOD_FACTS_ACCEPT_HEADER,
    OPEN_FOOD_FACTS_USER_AGENT,
    OpenFoodFactsFetchError,
    build_open_food_facts_url,
    fetch_open_food_facts_product,
    parse_open_food_facts_product,
)


def test_build_open_food_facts_url() -> None:
    assert (
        build_open_food_facts_url("3017620422003")
        == "https://world.openfoodfacts.org/api/v2/product/3017620422003.json"
    )


def test_parse_returns_none_when_status_not_found() -> None:
    assert parse_open_food_facts_product({"status": 0}, "3017620422003") is None


def test_parse_returns_none_when_product_missing() -> None:
    assert parse_open_food_facts_product({"status": 1}, "3017620422003") is None


def test_parse_builds_product_profile_from_valid_payload() -> None:
    payload = {
        "status": 1,
        "product": {
            "product_name": "Chocolate Spread",
            "brands": "Ferrero",
            "categories": "Spreads, Sweet spreads",
            "generic_name": "Hazelnut cocoa spread",
            "image_front_url": "https://example.com/front.jpg",
            "ingredients_text": "Sugar, hazelnuts, cocoa",
            "allergens_tags": ["en:milk", "en:nuts"],
            "nutriments": {
                "energy-kcal_100g": "530",
                "fat_100g": "30.9",
                "saturated-fat_100g": "10.6",
                "carbohydrates_100g": "57.5",
                "sugars_100g": "56.3",
                "proteins_100g": "6.3",
                "salt_100g": "0.11",
                "fiber_100g": "invalid",
            },
        },
    }

    profile = parse_open_food_facts_product(payload, "3017620422003")

    assert profile is not None
    assert profile.barcode == "3017620422003"
    assert profile.gtin == "3017620422003"
    assert profile.product_name == "Chocolate Spread"
    assert profile.brand == "Ferrero"
    assert profile.category == "Spreads, Sweet spreads"
    assert profile.images
    assert profile.nutrition is not None
    assert profile.nutrition.energy_kcal == 530.0
    assert profile.nutrition.fiber_g is None
    assert profile.ingredients == ["Sugar, hazelnuts, cocoa"]
    assert profile.allergens == ["en:milk", "en:nuts"]
    assert profile.evidence
    assert profile.confidence is not None
    assert 0 <= profile.confidence.overall <= 1


class _MockResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload.encode("utf-8")

    def __enter__(self) -> "_MockResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_fetch_sends_user_agent_and_accept_headers(monkeypatch) -> None:
    captured = {}

    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        captured["request"] = request
        return _MockResponse(json.dumps({"status": 0}))

    monkeypatch.setattr("app.extractors.open_food_facts.urlopen", mock_urlopen)

    fetch_open_food_facts_product("12345678")

    request = captured["request"]
    assert request.headers.get("User-agent") == OPEN_FOOD_FACTS_USER_AGENT
    assert request.headers.get("Accept") == OPEN_FOOD_FACTS_ACCEPT_HEADER


def test_fetch_returns_product_when_urlopen_mocked(monkeypatch) -> None:
    payload = {
        "status": 1,
        "product": {
            "product_name_en": "Test Product",
            "brands": "Test Brand",
            "categories": "Test Category",
            "image_url": "https://example.com/image.jpg",
            "nutriments": {"energy-kcal": 120},
        },
    }

    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        return _MockResponse(json.dumps(payload))

    monkeypatch.setattr("app.extractors.open_food_facts.urlopen", mock_urlopen)

    profile = fetch_open_food_facts_product("12345678")

    assert profile is not None
    assert profile.product_name == "Test Product"


def test_fetch_returns_none_when_status_is_not_found(monkeypatch) -> None:
    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        return _MockResponse(json.dumps({"status": 0}))

    monkeypatch.setattr("app.extractors.open_food_facts.urlopen", mock_urlopen)
    assert fetch_open_food_facts_product("12345678") is None


def test_fetch_raises_open_food_facts_fetch_error_for_url_error(monkeypatch) -> None:
    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        raise URLError("network down")

    monkeypatch.setattr("app.extractors.open_food_facts.urlopen", mock_urlopen)

    with pytest.raises(OpenFoodFactsFetchError, match="network error"):
        fetch_open_food_facts_product("12345678")


def test_fetch_raises_open_food_facts_fetch_error_for_http_error(monkeypatch) -> None:
    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        raise HTTPError(
            url="https://example.com",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("app.extractors.open_food_facts.urlopen", mock_urlopen)

    with pytest.raises(OpenFoodFactsFetchError, match="HTTP error: 503"):
        fetch_open_food_facts_product("12345678")


def test_fetch_raises_open_food_facts_fetch_error_for_invalid_json(monkeypatch) -> None:
    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        return _MockResponse("not json")

    monkeypatch.setattr("app.extractors.open_food_facts.urlopen", mock_urlopen)

    with pytest.raises(OpenFoodFactsFetchError, match="invalid JSON"):
        fetch_open_food_facts_product("12345678")


def test_fetch_raises_open_food_facts_fetch_error_when_payload_is_not_dict(monkeypatch) -> None:
    def mock_urlopen(request, timeout: float):  # noqa: ANN001,ARG001
        return _MockResponse(json.dumps([1, 2, 3]))

    monkeypatch.setattr("app.extractors.open_food_facts.urlopen", mock_urlopen)

    with pytest.raises(OpenFoodFactsFetchError, match="not a JSON object"):
        fetch_open_food_facts_product("12345678")
