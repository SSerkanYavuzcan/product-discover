import pytest
from psycopg.rows import dict_row

from app.storage.database_url import (
    is_postgres_url,
    normalize_database_backend,
    require_database_url_for_postgres,
)
from app.storage.postgres import (
    get_postgres_connection,
    initialize_postgres_database,
)


def test_normalize_database_backend_defaults_to_sqlite() -> None:
    assert normalize_database_backend(None) == "sqlite"
    assert normalize_database_backend("") == "sqlite"
    assert normalize_database_backend(" ") == "sqlite"


def test_normalize_database_backend_normalizes_whitespace_and_case() -> None:
    assert normalize_database_backend(" POSTGRES ") == "postgres"
    assert normalize_database_backend(" SQLite ") == "sqlite"


def test_normalize_database_backend_rejects_unsupported_backend() -> None:
    with pytest.raises(ValueError, match="Supported values"):
        normalize_database_backend("mysql")


def test_require_database_url_for_postgres_rules() -> None:
    assert require_database_url_for_postgres("sqlite", None) is None

    with pytest.raises(
        ValueError,
        match="DATABASE_URL is required when DATABASE_BACKEND is postgres",
    ):
        require_database_url_for_postgres("postgres", None)

    with pytest.raises(
        ValueError,
        match="DATABASE_URL is required when DATABASE_BACKEND is postgres",
    ):
        require_database_url_for_postgres("postgres", "   ")

    assert (
        require_database_url_for_postgres(
            " postgres ",
            " postgresql://user:pass@host/db ",
        )
        == "postgresql://user:pass@host/db"
    )


def test_is_postgres_url() -> None:
    assert is_postgres_url("postgresql://user:pass@host/db") is True
    assert is_postgres_url("postgres://user:pass@host/db") is True
    assert is_postgres_url("postgresql+psycopg://user:pass@host/db") is True
    assert is_postgres_url("sqlite:///data.db") is False


def test_get_postgres_connection_calls_psycopg_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_connection = object()
    captured: dict[str, object] = {}

    def fake_connect(url: str, *, row_factory: object) -> object:
        captured["url"] = url
        captured["row_factory"] = row_factory
        return fake_connection

    monkeypatch.setattr("app.storage.postgres.psycopg.connect", fake_connect)

    result = get_postgres_connection("postgresql://user:pass@host/db")

    assert result is fake_connection
    assert captured["url"] == "postgresql://user:pass@host/db"
    assert captured["row_factory"] is dict_row


def test_get_postgres_connection_rejects_blank_url() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        get_postgres_connection("   ")


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def execute(self, sql: str) -> None:
        self.calls.append(("execute", sql))

    def commit(self) -> None:
        self.calls.append(("commit", None))

    def close(self) -> None:
        self.calls.append(("close", None))


def test_initialize_postgres_database_executes_and_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_connection = _FakeConnection()

    def fake_get_connection(database_url: str) -> _FakeConnection:
        assert database_url == "postgresql://user:pass@host/db"
        return fake_connection

    monkeypatch.setattr("app.storage.postgres.get_postgres_connection", fake_get_connection)

    initialize_postgres_database(
        "postgresql://user:pass@host/db",
        "CREATE TABLE example(id INTEGER);",
    )

    assert fake_connection.calls == [
        ("execute", "CREATE TABLE example(id INTEGER);"),
        ("commit", None),
        ("close", None),
    ]
