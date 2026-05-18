from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from app.api import dependencies
from app.storage.postgres_adapter import (
    PostgresConnectionAdapter,
    translate_named_placeholders,
)
from app.storage.runtime import get_runtime_connection


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object | None]] = []

    def execute(self, sql: str, params: object | None = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> dict[str, str]:
        return {"value": "one"}

    def fetchall(self) -> list[dict[str, str]]:
        return [{"value": "one"}]

    def __iter__(self) -> Iterator[dict[str, str]]:
        return iter(self.fetchall())


class FakeRawConnection:
    def __init__(self) -> None:
        self.cursor_calls = 0
        self.last_cursor = FakeCursor()
        self.commit_calls = 0
        self.close_calls = 0

    def cursor(self) -> FakeCursor:
        self.cursor_calls += 1
        return self.last_cursor

    def commit(self) -> None:
        self.commit_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def test_sqlite_runtime_selection_preserves_behavior(tmp_path: pytest.TempPathFactory) -> None:
    database_path = str(tmp_path / "runtime.sqlite")

    with get_runtime_connection(
        database_backend="sqlite",
        database_path=database_path,
        database_url=None,
    ) as connection:
        assert isinstance(connection, sqlite3.Connection)
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
        ).fetchone()
        assert row is not None

    assert (tmp_path / "runtime.sqlite").exists()


def test_blank_backend_defaults_to_sqlite(tmp_path: pytest.TempPathFactory) -> None:
    database_path = str(tmp_path / "default.sqlite")

    with get_runtime_connection(
        database_backend="",
        database_path=database_path,
        database_url=None,
    ) as connection:
        assert isinstance(connection, sqlite3.Connection)
        row = connection.execute("SELECT 1").fetchone()
        assert row is not None


def test_postgres_runtime_requires_database_url(tmp_path: pytest.TempPathFactory) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        with get_runtime_connection(
            database_backend="postgres",
            database_path=str(tmp_path / "ignored.sqlite"),
            database_url=None,
        ):
            pass


def test_postgres_runtime_initializes_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_raw_connection = FakeRawConnection()

    monkeypatch.setattr(
        "app.storage.runtime.get_postgres_connection",
        lambda _database_url: fake_raw_connection,
    )

    with get_runtime_connection(
        database_backend="postgres",
        database_path="ignored.sqlite",
        database_url="postgresql://example",
    ) as connection:
        assert isinstance(connection, PostgresConnectionAdapter)

    executed_sql = "\n".join(sql for sql, _ in fake_raw_connection.last_cursor.executed)
    assert "CREATE TABLE IF NOT EXISTS products" in executed_sql
    assert fake_raw_connection.commit_calls == 1
    assert fake_raw_connection.close_calls == 1


def test_postgres_adapter_translates_qmark_placeholders() -> None:
    fake_raw_connection = FakeRawConnection()
    adapter = PostgresConnectionAdapter(fake_raw_connection)

    adapter.execute("SELECT * FROM products WHERE product_id = ?", ("p1",))

    sql, params = fake_raw_connection.last_cursor.executed[-1]
    assert "%s" in sql
    assert "?" not in sql
    assert params == ("p1",)


def test_postgres_adapter_translates_named_placeholders() -> None:
    fake_raw_connection = FakeRawConnection()
    adapter = PostgresConnectionAdapter(fake_raw_connection)

    adapter.execute(
        "INSERT INTO products (product_id, product_name) VALUES (:product_id, :product_name)",
        {"product_id": "p1", "product_name": "Name"},
    )

    sql, params = fake_raw_connection.last_cursor.executed[-1]
    assert "%(product_id)s" in sql
    assert "%(product_name)s" in sql
    assert params == {"product_id": "p1", "product_name": "Name"}


def test_translate_named_placeholders_preserves_postgres_casts() -> None:
    translated = translate_named_placeholders("SELECT now()::text AS value")
    assert translated == "SELECT now()::text AS value"


def test_executescript_executes_multiple_statements() -> None:
    fake_raw_connection = FakeRawConnection()
    adapter = PostgresConnectionAdapter(fake_raw_connection)

    adapter.executescript("CREATE TABLE a(id TEXT); CREATE INDEX idx_a ON a(id);")

    assert len(fake_raw_connection.last_cursor.executed) == 2


def test_dependencies_get_db_connection_uses_runtime_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}

    class FakeSettings:
        database_backend = "postgres"
        database_path = "path.sqlite"
        database_url = "postgresql://example"

    def fake_runtime_connection(**kwargs: object):
        captured_kwargs.update(kwargs)

        class _Ctx:
            def __enter__(self) -> str:
                return "db-connection"

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        return _Ctx()

    monkeypatch.setattr(dependencies, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(dependencies, "get_runtime_connection", fake_runtime_connection)

    generator = dependencies.get_db_connection()
    assert next(generator) == "db-connection"

    with pytest.raises(StopIteration):
        next(generator)

    assert captured_kwargs == {
        "database_backend": "postgres",
        "database_path": "path.sqlite",
        "database_url": "postgresql://example",
    }
