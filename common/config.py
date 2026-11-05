"""Configuration loading for the API test framework."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


@dataclass
class TestConfig:
    env: str
    description: str
    base_url: str
    db: dict[str, Any]
    users: dict[str, dict[str, str]]
    token_secret: str
    token_ttl_seconds: int
    timeout: float
    retries: int
    backoff_factor: float
    auto_start: bool
    health_path: str
    startup_timeout_seconds: int
    project_root: Path = field(default=PROJECT_ROOT)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def sqlite_path(self) -> Path:
        path = Path(self.db.get("sqlite_path", "runtime/book_admin.db"))
        return path if path.is_absolute() else self.project_root / path


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(env: str | None = None, config_path: Path | None = None) -> TestConfig:
    path = config_path or CONFIG_PATH
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    selected_env = env or os.getenv("API_ENV") or document.get("default_env", "dev")
    environments = document.get("environments", {})
    if selected_env not in environments:
        raise KeyError(f"Unknown environment '{selected_env}', available: {sorted(environments)}")

    raw = dict(document.get("common", {}))
    raw.update(environments[selected_env])
    db = dict(raw.get("db", {}))
    db_backend = os.getenv("DB_BACKEND", db.get("backend", "sqlite"))
    db["backend"] = db_backend
    if db_backend == "sqlite":
        db["sqlite_path"] = os.getenv(
            "SQLITE_PATH", db.get("sqlite_path", "runtime/book_admin.db")
        )
    else:
        for key, env_key in (
            ("host", "MYSQL_HOST"),
            ("port", "MYSQL_PORT"),
            ("user", "MYSQL_USER"),
            ("password", "MYSQL_PASSWORD"),
            ("database", "MYSQL_DATABASE"),
        ):
            if os.getenv(env_key):
                db[key] = os.getenv(env_key)
        db["port"] = int(db.get("port", 3306))

    auth = raw.get("auth", {})
    server = raw.get("server", {})
    http = raw.get("http", {})
    base_url = os.getenv("API_BASE_URL", raw["base_url"]).rstrip("/")
    auto_start_default = bool(server.get("auto_start", False))
    return TestConfig(
        env=selected_env,
        description=raw.get("description", ""),
        base_url=base_url,
        db=db,
        users=auth.get("users", {}),
        token_secret=os.getenv("TOKEN_SECRET", auth.get("token_secret", "book-admin-demo-secret")),
        token_ttl_seconds=int(auth.get("ttl_seconds", 3600)),
        timeout=float(os.getenv("HTTP_TIMEOUT", http.get("timeout", 5))),
        retries=int(os.getenv("HTTP_RETRIES", http.get("retries", 2))),
        backoff_factor=float(http.get("backoff_factor", 0.2)),
        auto_start=_as_bool(os.getenv("AUTO_START_SERVER"), auto_start_default),
        health_path=server.get("health_path", "/healthz"),
        startup_timeout_seconds=int(server.get("startup_timeout_seconds", 30)),
        raw=raw,
    )
