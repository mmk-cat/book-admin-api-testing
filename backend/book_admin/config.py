"""Runtime configuration for the Book Admin demo service.

The service intentionally keeps configuration in environment variables so the
same package can run against SQLite (zero-dependency local demo) and MySQL
(the stack used in the portfolio/CI environment).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "runtime" / "book_admin.db"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_backend: str
    sqlite_path: Path
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    token_secret: str
    token_ttl_seconds: int
    host: str
    port: int
    seed_demo_data: bool

    @classmethod
    def from_env(cls) -> "Settings":
        backend = os.getenv("DB_BACKEND", "sqlite").strip().lower()
        if backend not in {"sqlite", "mysql"}:
            raise ValueError("DB_BACKEND must be 'sqlite' or 'mysql'")
        return cls(
            db_backend=backend,
            sqlite_path=Path(os.getenv("SQLITE_PATH", str(DEFAULT_SQLITE_PATH))),
            mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            mysql_port=int(os.getenv("MYSQL_PORT", "3306")),
            mysql_user=os.getenv("MYSQL_USER", "book_admin"),
            mysql_password=os.getenv("MYSQL_PASSWORD", "book_admin_pwd"),
            mysql_database=os.getenv("MYSQL_DATABASE", "book_admin"),
            token_secret=os.getenv("TOKEN_SECRET", "book-admin-demo-secret"),
            token_ttl_seconds=int(os.getenv("TOKEN_TTL_SECONDS", "3600")),
            host=os.getenv("APP_HOST", "127.0.0.1"),
            port=int(os.getenv("APP_PORT", "5001")),
            seed_demo_data=_env_bool("SEED_DEMO_DATA", True),
        )
