"""Flask application factory for the Book Admin demo service."""

from __future__ import annotations

import logging
import re
import sys
import time
import uuid
from pathlib import Path

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from .api import api
from .config import Settings
from .db import Database
from .security import ApiError

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _configure_logging() -> logging.Logger:
    logger = logging.getLogger("book_admin")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
    )
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    logger.propagate = False
    return logger


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.request_id = g.request_id
        except (AttributeError, RuntimeError):
            record.request_id = "-"
        return True


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_env()
    database = Database(settings)
    database.init_schema()

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.config.update(
        TESTING=False,
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    app.extensions["settings"] = settings
    app.extensions["db"] = database

    logger = _configure_logging()
    for handler in logger.handlers:
        handler.addFilter(_RequestIdFilter())

    @app.before_request
    def attach_request_context():
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex
        g.started_at = time.perf_counter()

    @app.after_request
    def add_trace_headers(response):
        elapsed_ms = (time.perf_counter() - getattr(g, "started_at", time.perf_counter())) * 1000
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        if response.is_json:
            response.headers["Content-Type"] = "application/json; charset=utf-8"
        logger.info(
            "%s %s -> %s %.2fms",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        payload = {
            "code": error.code,
            "message": error.message,
            "data": None,
            "request_id": getattr(g, "request_id", ""),
        }
        if error.details is not None:
            payload["details"] = error.details
        return jsonify(payload), error.status

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        code_map = {404: 40400, 405: 40500, 413: 41300, 415: 41500}
        payload = {
            "code": code_map.get(error.code or 500, 50000),
            "message": error.description or "HTTP error",
            "data": None,
            "request_id": getattr(g, "request_id", ""),
        }
        return jsonify(payload), error.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        logger.exception("Unhandled exception: %s", error)
        return (
            jsonify(
                {
                    "code": 50000,
                    "message": "服务器内部错误",
                    "data": None,
                    "request_id": getattr(g, "request_id", ""),
                }
            ),
            500,
        )

    @app.get("/healthz")
    def healthz():
        healthy = database.ping()
        return jsonify(
            {
                "status": "ok" if healthy else "degraded",
                "db_backend": database.backend,
            }
        ), (200 if healthy else 503)

    app.register_blueprint(api)
    logger.info(
        "Book Admin started (db=%s, sqlite=%s, mysql=%s/%s)",
        settings.db_backend,
        settings.sqlite_path,
        settings.mysql_host,
        settings.mysql_database,
    )
    return app
