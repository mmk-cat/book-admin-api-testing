"""Small DB-API abstraction used by the demo service.

Both SQLite and MySQL are supported.  SQLite keeps the repository runnable on
a laptop without a database server; MySQL is the configuration used by CI and
is the one exercised by the ``pymysql`` persistence assertions.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from werkzeug.security import generate_password_hash

from .config import Settings

try:  # MySQL is optional for the zero-dependency demo.
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # pragma: no cover - exercised on machines without PyMySQL
    pymysql = None
    DictCursor = None


def utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.backend = settings.db_backend
        if self.backend == "mysql" and pymysql is None:
            raise RuntimeError("DB_BACKEND=mysql requires PyMySQL to be installed")

    # ------------------------------------------------------------------ connections
    def connect(self) -> Any:
        if self.backend == "sqlite":
            path = Path(self.settings.sqlite_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path), timeout=15)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        assert pymysql is not None
        return pymysql.connect(
            host=self.settings.mysql_host,
            port=self.settings.mysql_port,
            user=self.settings.mysql_user,
            password=self.settings.mysql_password,
            database=self.settings.mysql_database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.backend == "mysql" else sql

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------ queries
    def _rows(self, cursor: Any) -> list[dict[str, Any]]:
        rows = cursor.fetchall()
        if self.backend == "sqlite":
            return [dict(row) for row in rows]
        return [dict(row) for row in rows]

    def query_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(self._sql(sql), tuple(params))
            return self._rows(cursor)
        finally:
            conn.close()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.query_all(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> dict[str, int]:
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(self._sql(sql), tuple(params))
            return {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid or 0}

    # ------------------------------------------------------------------ schema / seed
    def init_schema(self, seed: bool | None = None) -> None:
        if self.backend == "sqlite":
            path = Path(self.settings.sqlite_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            schema = Path(__file__).with_name("sql") / "schema_sqlite.sql"
            conn = self.connect()
            try:
                conn.executescript(schema.read_text(encoding="utf-8"))
                conn.commit()
            finally:
                conn.close()
        else:
            self._init_mysql_schema()
        should_seed = self.settings.seed_demo_data if seed is None else seed
        if should_seed:
            self.seed_if_empty()

    def _init_mysql_schema(self) -> None:
        assert pymysql is not None
        db_name = self.settings.mysql_database
        if not db_name.replace("_", "").isalnum():
            raise ValueError("MYSQL_DATABASE may only contain letters, digits and underscores")
        admin = pymysql.connect(
            host=self.settings.mysql_host,
            port=self.settings.mysql_port,
            user=self.settings.mysql_user,
            password=self.settings.mysql_password,
            charset="utf8mb4",
            autocommit=True,
        )
        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        finally:
            admin.close()

        schema_path = Path(__file__).with_name("sql") / "schema_mysql.sql"
        statements = [part.strip() for part in schema_path.read_text(encoding="utf-8").split(";") if part.strip()]
        with self.transaction() as conn:
            cursor = conn.cursor()
            for statement in statements:
                cursor.execute(statement)

    def seed_if_empty(self) -> None:
        row = self.query_one("SELECT COUNT(*) AS total FROM users")
        if row and int(row["total"]) > 0:
            return
        now = utc_now_str()
        users = [
            ("admin", generate_password_hash("admin123"), "admin", "active", now),
            ("reader", generate_password_hash("reader123"), "reader", "active", now),
            ("reader2", generate_password_hash("reader123"), "reader", "active", now),
            ("disabled", generate_password_hash("disabled123"), "reader", "disabled", now),
        ]
        books = [
            ("9787115000001", "Python自动化测试实战", "陈磊", "科技", 89.00, 8, "available"),
            ("9787115000002", "软件测试的艺术", "梅尔斯", "科技", 59.00, 5, "available"),
            ("9787115000003", "接口自动化测试", "周明", "科技", 69.00, 6, "available"),
            ("9787115000004", "SQL必知必会", "福达", "科技", 49.00, 10, "available"),
            ("9787115000005", "数据仓库工具箱", "金博尔", "科技", 129.00, 3, "off_shelf"),
            ("9787115000006", "大数据之路", "阿里巴巴数据技术", "科技", 79.00, 0, "borrowed"),
            ("9787115000007", "深入理解计算机系统", "布莱恩特", "科技", 139.00, 4, "available"),
            ("9787115000008", "代码整洁之道", "马丁", "科技", 59.00, 7, "available"),
            ("9787115000009", "活着", "余华", "文学", 45.00, 12, "available"),
            ("9787115000010", "百年孤独", "马尔克斯", "文学", 55.00, 6, "available"),
            ("9787115000011", "人类简史", "赫拉利", "历史", 68.00, 9, "available"),
            ("9787115000012", "明朝那些事儿", "当年明月", "历史", 299.00, 2, "available"),
            ("9787115000013", "经济学原理", "曼昆", "经管", 88.00, 5, "available"),
            ("9787115000014", "穷查理宝典", "芒格", "经管", 98.00, 3, "available"),
            ("9787115000015", "小王子", "圣埃克苏佩里", "少儿", 35.00, 15, "available"),
            ("9787115000016", "解忧杂货店", "东野圭吾", "文学", 39.50, 8, "available"),
            ("9787115000017", "算法导论", "科尔曼", "科技", 128.00, 5, "available"),
            ("9787115000018", "深度学习", "古德费洛", "科技", 168.00, 4, "available"),
            ("9787115000019", "机器学习", "周志华", "科技", 88.00, 6, "available"),
            ("9787115000020", "统计学习方法", "李航", "科技", 78.00, 3, "available"),
            ("9787115000021", "三体", "刘慈欣", "文学", 93.00, 11, "available"),
            ("9787115000022", "流浪地球", "刘慈欣", "文学", 42.00, 0, "borrowed"),
            ("9787115000023", "中国通史", "吕思勉", "历史", 108.00, 2, "off_shelf"),
            ("9787115000024", "万历十五年", "黄仁宇", "历史", 56.00, 5, "available"),
        ]
        with self.transaction() as conn:
            cursor = conn.cursor()
            user_sql = (
                "INSERT INTO users (username, password_hash, role, status, created_at) "
                "VALUES (?, ?, ?, ?, ?)"
            )
            book_sql = (
                "INSERT INTO books (isbn, title, author, category, price, stock, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            cursor.executemany(self._sql(user_sql), users)
            cursor.executemany(
                self._sql(book_sql),
                [(isbn, title, author, category, price, stock, status, now, now)
                 for isbn, title, author, category, price, stock, status in books],
            )

    # ------------------------------------------------------------------ health
    def ping(self) -> bool:
        try:
            return self.query_one("SELECT 1 AS ok") is not None
        except Exception:
            return False
