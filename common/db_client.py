"""Direct database assertions, including the pymysql path used in CI."""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable

from .config import TestConfig


class DBClient:
    def __init__(self, config: TestConfig) -> None:
        self.config = config
        self.backend = config.db["backend"]

    def _connect(self):
        if self.backend == "sqlite":
            conn = sqlite3.connect(str(self.config.sqlite_path), timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        import pymysql
        from pymysql.cursors import DictCursor

        return pymysql.connect(
            host=self.config.db.get("host", "127.0.0.1"),
            port=int(self.config.db.get("port", 3306)),
            user=self.config.db.get("user"),
            password=self.config.db.get("password"),
            database=self.config.db.get("database"),
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True,
        )

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.backend == "mysql" else sql

    def query_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(self._sql(sql), tuple(params))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.query_all(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Iterable[Any] = ()) -> Any:
        row = self.query_one(sql, params)
        return next(iter(row.values())) if row else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(self._sql(sql), tuple(params))
            if self.backend == "sqlite":
                conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def book_by_isbn(self, isbn: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM books WHERE isbn = ?", (isbn,))

    def book_by_id(self, book_id: int) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM books WHERE id = ?", (book_id,))

    def column_types(self, table: str) -> dict[str, str]:
        if table not in {"users", "books", "borrows", "auth_tokens"}:
            raise ValueError("unexpected table")
        if self.backend == "sqlite":
            rows = self.query_all(f"PRAGMA table_info({table})")
            return {row["name"]: str(row["type"]).upper() for row in rows}
        rows = self.query_all(
            "SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            (self.config.db.get("database"), table),
        )
        return {row["COLUMN_NAME"]: str(row["COLUMN_TYPE"]).lower() for row in rows}

    def cleanup_book(self, book_id: int) -> None:
        self.execute("DELETE FROM borrows WHERE book_id = ?", (book_id,))
        self.execute("DELETE FROM books WHERE id = ?", (book_id,))
