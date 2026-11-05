"""Assertion helpers with rich failure output (including Allure attachments)."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
import requests

try:
    import allure
except ImportError:  # pragma: no cover
    allure = None


def _attach_response(response: requests.Response) -> None:
    if allure is None:
        return
    try:
        allure.attach(
            response.text,
            name=f"response-{response.status_code}",
            attachment_type=allure.attachment_type.JSON
            if response.headers.get("Content-Type", "").startswith("application/json")
            else allure.attachment_type.TEXT,
        )
        allure.attach(
            json.dumps(dict(response.headers), ensure_ascii=False, indent=2),
            name="response-headers",
            attachment_type=allure.attachment_type.JSON,
        )
    except Exception:
        pass


def fail_with_response(message: str, response: requests.Response) -> None:
    _attach_response(response)
    pytest.fail(
        f"{message}\n"
        f"HTTP {response.status_code} {response.request.method} {response.url}\n"
        f"body={response.text[:4000]}"
    )


def body(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        fail_with_response("Response is not valid JSON", response)
        raise
    if not isinstance(payload, dict):
        fail_with_response("Response JSON must be an object", response)
    return payload


def expect_status(response: requests.Response, status: int) -> None:
    if response.status_code != status:
        fail_with_response(f"Expected HTTP {status}", response)


def expect_error(
    response: requests.Response,
    *,
    status: int,
    code: int,
    field: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    expect_status(response, status)
    payload = body(response)
    if payload.get("code") != code:
        fail_with_response(f"Expected business code {code}, got {payload.get('code')}", response)
    if field:
        actual_field = (payload.get("details") or {}).get("field")
        if actual_field != field:
            fail_with_response(f"Expected error field '{field}', got '{actual_field}'", response)
    if reason:
        actual_reason = (payload.get("details") or {}).get("reason")
        if actual_reason != reason:
            fail_with_response(f"Expected reason '{reason}', got '{actual_reason}'", response)
    return payload


def expect_ok(response: requests.Response, status: int = 200) -> dict[str, Any]:
    expect_status(response, status)
    payload = body(response)
    if payload.get("code") != 0:
        fail_with_response("Expected success envelope code=0", response)
    if "request_id" not in payload or not payload["request_id"]:
        fail_with_response("Success envelope is missing request_id", response)
    return payload


def expect_book_shape(book: dict[str, Any]) -> None:
    required = {
        "id": int,
        "isbn": str,
        "title": str,
        "author": str,
        "category": str,
        "price": (int, float),
        "stock": int,
        "status": str,
        "created_at": str,
        "updated_at": str,
    }
    for name, expected_type in required.items():
        if name not in book:
            pytest.fail(f"book field '{name}' is missing: {book}")
        value = book[name]
        if not isinstance(value, expected_type) or isinstance(value, bool):
            pytest.fail(f"book field '{name}' has wrong type {type(value)!r}: {book}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", book["created_at"]):
        pytest.fail(f"created_at is not ISO-8601 UTC: {book['created_at']}")


def expect_pagination(payload: dict[str, Any], *, page: int, page_size: int) -> None:
    data = payload.get("data") or {}
    pagination = data.get("pagination") or {}
    if pagination.get("page") != page or pagination.get("page_size") != page_size:
        pytest.fail(f"Unexpected pagination: {pagination}, expected page={page} page_size={page_size}")
    items = data.get("items")
    if not isinstance(items, list):
        pytest.fail(f"data.items is not a list: {data}")


def assert_db_value(db, sql: str, params, column: str, expected: Any) -> None:
    row = db.query_one(sql, params)
    if row is None:
        pytest.fail(f"No DB row for query: {sql} params={params}")
    if row[column] != expected:
        pytest.fail(f"DB column {column}: expected {expected!r}, got {row[column]!r} ({row})")
