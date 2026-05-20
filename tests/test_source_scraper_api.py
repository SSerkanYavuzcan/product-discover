import sqlite3
from collections.abc import Iterator

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection
from app.main import app
from app.sources import SourceRegistry, create_source
from app.storage.database import get_connection, initialize_database


def _override_db(db_path: str):
    def override() -> Iterator[sqlite3.Connection]:
        connection = get_connection(db_path)
        try:
            yield connection
        finally:
            connection.close()

    return override


def test_scraper_capability_true_for_kimgeldi(tmp_path) -> None:
    db_path = tmp_path / "scraper_cap.db"
    initialize_database(str(db_path))
    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    try:
        with get_connection(str(db_path)) as connection:
            source = create_source(
                connection,
                SourceRegistry(
                    source_name="Kimgeldi",
                    source_type="website",
                    base_url="https://kimgeldi.com",
                ),
            )
        response = TestClient(app).get(f"/sources/{source.source_id}/scraper-capability")
        assert response.status_code == 200
        payload = response.json()
        assert payload["has_custom_scraper"] is True
        assert payload["scraper_name"] == "KimgeldiScraper"
    finally:
        app.dependency_overrides.clear()


def test_scraper_capability_false_for_unknown_source(tmp_path) -> None:
    db_path = tmp_path / "scraper_cap_missing.db"
    initialize_database(str(db_path))
    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    try:
        response = TestClient(app).get("/sources/missing/scraper-capability")
        assert response.status_code == 200
        assert response.json()["has_custom_scraper"] is False
    finally:
        app.dependency_overrides.clear()


def test_scrape_source_404_for_unknown_source(tmp_path) -> None:
    db_path = tmp_path / "scrape_missing.db"
    initialize_database(str(db_path))
    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))
    try:
        response = TestClient(app).post("/sources/missing/scrape", json={"limit": 10})
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_scrape_uses_custom_scraper_and_returns_counts(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "scrape_custom.db"
    initialize_database(str(db_path))
    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))

    from app.scrapers.base import ScrapedProduct
    from app.scrapers.kimgeldi import KimgeldiScraper

    def fake_scrape(self, source, limit=100):  # noqa: ANN001
        del self, source, limit
        return [ScrapedProduct(product_name="Demo", source_url="https://kimgeldi.com/urun/demo")]

    monkeypatch.setattr(KimgeldiScraper, "scrape", fake_scrape)
    try:
        with get_connection(str(db_path)) as connection:
            source = create_source(
                connection,
                SourceRegistry(
                    source_name="Kimgeldi",
                    source_type="website",
                    base_url="https://kimgeldi.com",
                ),
            )
        response = TestClient(app).post(f"/sources/{source.source_id}/scrape", json={"limit": 10})
        assert response.status_code == 200
        payload = response.json()
        assert payload["method"] == "custom_scraper"
        assert payload["scraper_name"] == "KimgeldiScraper"
        assert payload["scraped_count"] == 1
        assert payload["persisted_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_scrape_custom_scraper_deduplicates_same_product(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "scrape_custom_dupe.db"
    initialize_database(str(db_path))
    app.dependency_overrides[get_db_connection] = _override_db(str(db_path))

    from app.scrapers.base import ScrapedProduct
    from app.scrapers.kimgeldi import KimgeldiScraper

    def fake_scrape(self, source, limit=100):  # noqa: ANN001
        del self, source, limit
        return [
            ScrapedProduct(product_name="Demo", source_url="https://kimgeldi.com/urun/demo"),
            ScrapedProduct(product_name=" Demo ", source_url="https://kimgeldi.com/urun/demo"),
        ]

    monkeypatch.setattr(KimgeldiScraper, "scrape", fake_scrape)
    try:
        with get_connection(str(db_path)) as connection:
            source = create_source(
                connection,
                SourceRegistry(
                    source_name="Kimgeldi",
                    source_type="website",
                    base_url="https://kimgeldi.com",
                ),
            )
        response = TestClient(app).post(f"/sources/{source.source_id}/scrape", json={"limit": 10})
        assert response.status_code == 200
        payload = response.json()
        assert payload["scraped_count"] == 2
        assert payload["persisted_count"] == 2
        with get_connection(str(db_path)) as connection:
            count = connection.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
        assert count == 1
    finally:
        app.dependency_overrides.clear()
