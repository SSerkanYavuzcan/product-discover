from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.config import Settings


def _build_app(allowed_origins: str) -> FastAPI:
    app = FastAPI()
    origins = Settings(allowed_origins=allowed_origins).get_allowed_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_get_allowed_origins_returns_empty_list_for_empty_input() -> None:
    assert Settings(allowed_origins="").get_allowed_origins() == []
    assert Settings(allowed_origins="   ").get_allowed_origins() == []


def test_get_allowed_origins_parses_comma_separated_list() -> None:
    origins = Settings(
        allowed_origins="https://example.com,https://app.example.com",
    ).get_allowed_origins()
    assert origins == ["https://example.com", "https://app.example.com"]


def test_get_allowed_origins_strips_and_ignores_empty_values() -> None:
    origins = Settings(
        allowed_origins=" https://example.com , , https://app.example.com ,, ",
    ).get_allowed_origins()
    assert origins == ["https://example.com", "https://app.example.com"]


def test_cors_preflight_returns_allow_origin_for_configured_origin() -> None:
    app = _build_app("https://frontend.example.com")
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "https://frontend.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://frontend.example.com"


def test_cors_headers_absent_when_origins_not_configured() -> None:
    app = _build_app("")
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "https://frontend.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers.get("access-control-allow-origin") is None
