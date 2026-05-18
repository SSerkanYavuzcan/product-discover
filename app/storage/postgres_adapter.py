"""Adapters for using sqlite-style repository calls with psycopg connections."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import Any

_NAMED_PLACEHOLDER_PATTERN = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


class PostgresCursorAdapter:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    def __iter__(self) -> Iterator[Any]:
        return iter(self._cursor)


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
