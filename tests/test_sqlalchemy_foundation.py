import pytest
from sqlalchemy.engine import Engine

from app.storage.orm_models import Base
from app.storage.sqlalchemy import create_sqlalchemy_engine, get_sqlalchemy_database_url


def test_get_sqlalchemy_database_url_for_sqlite_backend() -> None:
    url = get_sqlalchemy_database_url("sqlite", "data/product_discover_agent.db", None)
    assert url == "sqlite:///data/product_discover_agent.db"


def test_get_sqlalchemy_database_url_treats_empty_backend_as_sqlite() -> None:
    url = get_sqlalchemy_database_url("   ", "data/local.db", None)
    assert url == "sqlite:///data/local.db"


def test_get_sqlalchemy_database_url_for_postgres_backend() -> None:
    url = get_sqlalchemy_database_url("postgres", "ignored.db", "postgresql://user:pass@host/db")
    assert url == "postgresql://user:pass@host/db"


def test_get_sqlalchemy_database_url_raises_for_missing_postgres_url() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        get_sqlalchemy_database_url("postgres", "ignored.db", None)


def test_get_sqlalchemy_database_url_raises_for_unsupported_backend() -> None:
    with pytest.raises(ValueError, match="Unsupported database backend"):
        get_sqlalchemy_database_url("mysql", "ignored.db", None)


def test_orm_metadata_contains_expected_tables() -> None:
    table_names = set(Base.metadata.tables.keys())
    assert {"products", "product_evidence", "discovery_jobs", "batch_jobs"}.issubset(table_names)


def test_create_sqlalchemy_engine_returns_engine() -> None:
    engine = create_sqlalchemy_engine("sqlite:///data/product_discover_agent.db")
    assert isinstance(engine, Engine)
