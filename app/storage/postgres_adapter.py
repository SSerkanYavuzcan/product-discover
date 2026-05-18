"""Adapters for using sqlite-style repository calls with psycopg connections."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import Any

_NAMED_PLACEHOLDER_PATTERN = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


class PostgresRowAdapter:
    def __init__(self, row: object) -> None:
        self._row = row

    def __getitem__(self, key: str | int) -> object:
        if isinstance(key, int):
            if isinstance(self._row, Mapping):
                return list(self._row.values())[key]
            if isinstance(self._row, tuple | list):
                return self._row[key]
            raise KeyError(key)

        if isinstance(self._row, Mapping):
            return self._row[key]

        raise KeyError(key)

    def get(self, key: str, default: object | None = None) -> object | None:
        if isinstance(self._row, Mapping):
            return self._row.get(key, default)
        return default

    def keys(self):
        if isinstance(self._row, Mapping):
            return self._row.keys()
        return ()

    def values(self):
        if isinstance(self._row, Mapping):
            return self._row.values()
        if isinstance(self._row, tuple | list):
            return self._row
        return ()

    def items(self):
        if isinstance(self._row, Mapping):
            return self._row.items()
        return ()

    def __iter__(self):
        if isinstance(self._row, Mapping):
            return iter(self._row)
        if isinstance(self._row, tuple | list):
            return iter(self._row)
        return iter(())


class PostgresCursorAdapter:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self) -> PostgresRowAdapter | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return PostgresRowAdapter(row)

    def fetchall(self) -> list[PostgresRowAdapter]:
        return [PostgresRowAdapter(row) for row in self._cursor.fetchall()]

    def __iter__(self) -> Iterator[PostgresRowAdapter]:
        for row in self._cursor:
            yield PostgresRowAdapter(row)


class PostgresConnectionAdapter:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def execute(
        self,
        sql: str,
        parameters: object | None = None,
    ) -> PostgresCursorAdapter:
        translated_sql = translate_sqlite_placeholders(sql, parameters)
        cursor = self._connection.cursor()

        if parameters is None:
            cursor.execute(translated_sql)
        else:
            cursor.execute(translated_sql, parameters)

        return PostgresCursorAdapter(cursor)

    def executescript(self, sql_script: str) -> None:
        for statement in sql_script.split(";"):
            normalized = statement.strip()
            if normalized:
                self.execute(normalized)

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()


def translate_sqlite_placeholders(sql: str, parameters: object | None = None) -> str:
    if parameters is None:
        return translate_named_placeholders(translate_qmark_placeholders(sql))

    if isinstance(parameters, Mapping):
        return translate_named_placeholders(sql)

    if _is_sequence_parameters(parameters):
        return translate_qmark_placeholders(sql)

    return sql


def _is_sequence_parameters(parameters: object) -> bool:
    return isinstance(parameters, tuple | list)


def translate_qmark_placeholders(sql: str) -> str:
    return sql.replace("?", "%s")


def translate_named_placeholders(sql: str) -> str:
    return _NAMED_PLACEHOLDER_PATTERN.sub(r"%(\1)s", sql)
