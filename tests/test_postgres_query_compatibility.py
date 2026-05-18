from __future__ import annotations

from collections.abc import Iterator

from app.dashboard.summary import _count, get_dashboard_summary
from app.storage.postgres_adapter import PostgresCursorAdapter, PostgresRowAdapter


class FakeCursor:
    def __init__(self, one=None, many=None) -> None:
        self._one = one
        self._many = many or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many

    def __iter__(self) -> Iterator[object]:
        return iter(self._many)


class FakeResult:
    def __init__(self, row: object) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self, row: object) -> None:
        self.row = row

    def execute(self, _query: str, _params: tuple[object, ...] = ()) -> FakeResult:
        return FakeResult(self.row)


class DictValuesOnlyRow:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data

    def values(self):
        return self.data.values()


class RecordingConnection:
    def __init__(self) -> None:
        self.executed_queries: list[str] = []

    def execute(self, query: str, _params: tuple[object, ...] = ()) -> FakeResult:
        self.executed_queries.append(" ".join(query.split()))

        if "FROM extraction_runs" in query:
            return FakeResult(None)

        return FakeResult([0])


def test_postgres_row_adapter_supports_key_and_index_access_for_dict_rows() -> None:
    row = PostgresRowAdapter({"count": 3, "name": "x"})

    assert row["count"] == 3
    assert row[0] == 3
    assert row["name"] == "x"
    assert row[1] == "x"


def test_postgres_cursor_adapter_fetchone_wraps_dict_row() -> None:
    cursor = PostgresCursorAdapter(FakeCursor(one={"count": 5}))
    row = cursor.fetchone()

    assert row is not None
    assert row[0] == 5
    assert row["count"] == 5


def test_postgres_cursor_adapter_fetchall_wraps_dict_rows() -> None:
    cursor = PostgresCursorAdapter(FakeCursor(many=[{"count": 1}, {"count": 2}]))
    rows = cursor.fetchall()

    assert rows[0][0] == 1
    assert rows[1]["count"] == 2


def test_dashboard_count_works_with_indexed_row() -> None:
    connection = FakeConnection([7])
    assert _count(connection, "SELECT COUNT(*) FROM anything") == 7


def test_dashboard_count_works_with_dict_like_row_values() -> None:
    connection = FakeConnection(DictValuesOnlyRow({"count": 8}))
    assert _count(connection, "SELECT COUNT(*) FROM anything") == 8


def test_dashboard_summary_uses_substr_for_today_filters() -> None:
    connection = RecordingConnection()

    get_dashboard_summary(connection)

    assert any("substr(first_seen_at, 1, 10)" in query for query in connection.executed_queries)
    assert any("substr(created_at, 1, 10)" in query for query in connection.executed_queries)
    assert not any("DATE(first_seen_at)" in query for query in connection.executed_queries)
    assert not any("DATE(created_at)" in query for query in connection.executed_queries)
