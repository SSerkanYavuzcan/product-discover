import pytest

from app.config import Settings


def test_default_settings_use_sqlite_backend() -> None:
    settings = Settings()
    assert settings.get_database_backend() == "sqlite"


def test_database_backend_is_normalized_to_lowercase() -> None:
    settings = Settings(database_backend="POSTGRES")
    assert settings.get_database_backend() == "postgres"


def test_database_backend_whitespace_is_ignored() -> None:
    settings = Settings(database_backend="  sqlite  ")
    assert settings.get_database_backend() == "sqlite"


def test_unsupported_database_backend_raises_value_error() -> None:
    settings = Settings(database_backend="mysql")
    with pytest.raises(ValueError, match="Unsupported database backend"):
        settings.get_database_backend()


def test_is_sqlite_returns_true_for_sqlite() -> None:
    settings = Settings(database_backend="sqlite")
    assert settings.is_sqlite() is True


def test_is_postgres_returns_true_for_postgres() -> None:
    settings = Settings(database_backend="postgres")
    assert settings.is_postgres() is True


def test_require_database_url_for_postgres_does_not_raise_for_sqlite() -> None:
    settings = Settings(database_backend="sqlite", database_url=None)
    settings.require_database_url_for_postgres()


def test_require_database_url_for_postgres_raises_when_missing() -> None:
    settings = Settings(database_backend="postgres", database_url=None)
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        settings.require_database_url_for_postgres()


def test_require_database_url_for_postgres_does_not_raise_when_present() -> None:
    settings = Settings(database_backend="postgres", database_url="postgresql://user:pass@host/db")
    settings.require_database_url_for_postgres()


def test_database_path_default_remains_unchanged() -> None:
    settings = Settings()
    assert settings.database_path == "data/product_discover_agent.db"
