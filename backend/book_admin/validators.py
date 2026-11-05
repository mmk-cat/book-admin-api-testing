"""Request validation helpers with strict JSON type checking.

Python treats ``True`` as an ``int``; a book API must not.  The helpers below
reject booleans for numeric fields and avoid coercing strings, so type-error
tests exercise the same contract that the frontend consumes.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from flask import request

from .security import ApiError

CATEGORIES = ("科技", "文学", "历史", "经管", "少儿")
BOOK_STATUSES = ("available", "borrowed", "off_shelf")
BORROW_STATUSES = ("borrowed", "returned")
SORT_FIELDS = {"created_at", "price", "title", "stock"}
SORT_ORDERS = {"asc", "desc"}
ISBN_PATTERN = re.compile(r"(?:97[89]\d{10}|\d{9}[\dX])")


def bad_request(message: str, field: str | None = None, reason: str | None = None) -> ApiError:
    details = {}
    if field:
        details["field"] = field
    if reason:
        details["reason"] = reason
    return ApiError(400, 40001, message, details or None)


def require_json_object() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise bad_request("请求体必须是 JSON 对象", reason="invalid_json")
    return data


def require_fields(data: dict[str, Any], fields: Iterable[str]) -> None:
    missing = [field for field in fields if field not in data]
    if missing:
        raise ApiError(
            400,
            40002,
            f"缺少必填字段: {', '.join(missing)}",
            {"missing_fields": missing},
        )


def parse_str(data: dict[str, Any], field: str, *, min_len: int = 1,
              max_len: int = 255, allow_blank: bool = False, strip: bool = True) -> str:
    value = data.get(field)
    if value is None:
        raise bad_request(f"{field} 不能为空", field, "null")
    if not isinstance(value, str):
        raise bad_request(f"{field} 必须是字符串", field, "type")
    value = value.strip() if strip else value
    if not allow_blank and not value:
        raise bad_request(f"{field} 不能为空", field, "blank")
    if len(value) < min_len:
        raise bad_request(f"{field} 长度不能小于 {min_len}", field, "min_length")
    if len(value) > max_len:
        raise bad_request(f"{field} 长度不能超过 {max_len}", field, "max_length")
    return value


def parse_int(data: dict[str, Any], field: str, *, minimum: int = 0,
              maximum: int = 2_147_483_647, default: Any = None) -> int:
    if field not in data:
        if default is not None:
            return int(default)
        raise ApiError(400, 40002, f"缺少必填字段: {field}", {"missing_fields": [field]})
    value = data[field]
    if isinstance(value, bool) or not isinstance(value, int):
        raise bad_request(f"{field} 必须是整数", field, "type")
    if value < minimum or value > maximum:
        raise bad_request(f"{field} 必须在 {minimum} 到 {maximum} 之间", field, "range")
    return value


def parse_price(data: dict[str, Any], field: str = "price") -> Decimal:
    if field not in data:
        raise ApiError(400, 40002, f"缺少必填字段: {field}", {"missing_fields": [field]})
    value = data[field]
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise bad_request(f"{field} 必须是数字", field, "type")
    if isinstance(value, str):
        # Strings are accepted by JSON APIs in some clients, but this API is
        # intentionally strict.  Keep the explicit branch for a clear message.
        raise bad_request(f"{field} 必须是数字", field, "type")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise bad_request(f"{field} 必须是数字", field, "type") from exc
    if not amount.is_finite():
        raise bad_request(f"{field} 必须是有限数字", field, "type")
    if amount < 0 or amount > Decimal("9999"):
        raise bad_request(f"{field} 必须在 0 到 9999 之间", field, "range")
    exponent = amount.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise bad_request(f"{field} 最多保留两位小数", field, "precision")
    return amount


def parse_enum(data: dict[str, Any], field: str, allowed: Iterable[str]) -> str:
    value = data.get(field)
    if value is None:
        raise bad_request(f"{field} 不能为空", field, "null")
    if not isinstance(value, str):
        raise bad_request(f"{field} 必须是字符串", field, "type")
    if value not in allowed:
        raise bad_request(f"{field} 取值非法", field, "enum")
    return value


def parse_isbn(data: dict[str, Any]) -> str:
    value = parse_str(data, "isbn", min_len=10, max_len=13)
    normalized = value.replace("-", "").upper()
    if not ISBN_PATTERN.fullmatch(normalized):
        raise bad_request("isbn 格式不合法", "isbn", "format")
    return normalized


def parse_book_payload(data: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    required = ("isbn", "title", "author", "category", "price", "stock")
    if not partial:
        require_fields(data, required)
    allowed = set(required) | {"status"}
    if partial and not (allowed & set(data)):
        raise bad_request("至少提供一个可更新字段", reason="empty_update")
    result: dict[str, Any] = {}
    if not partial or "isbn" in data:
        result["isbn"] = parse_isbn(data)
    if not partial or "title" in data:
        result["title"] = parse_str(data, "title", min_len=1, max_len=100)
    if not partial or "author" in data:
        result["author"] = parse_str(data, "author", min_len=1, max_len=50)
    if not partial or "category" in data:
        result["category"] = parse_enum(data, "category", CATEGORIES)
    if not partial or "price" in data:
        result["price"] = str(parse_price(data))
    if not partial or "stock" in data:
        result["stock"] = parse_int(data, "stock", minimum=0, maximum=999)
    if "status" in data:
        result["status"] = parse_enum(data, "status", BOOK_STATUSES)
    return result


def query_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    if not re.fullmatch(r"\d+", raw):
        raise bad_request(f"{name} 必须是整数", name, "type")
    value = int(raw)
    if value < minimum or value > maximum:
        raise bad_request(f"{name} 必须在 {minimum} 到 {maximum} 之间", name, "range")
    return value


def query_enum(name: str, allowed: Iterable[str]) -> str | None:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    allowed_tuple = tuple(allowed)
    if raw not in allowed_tuple:
        raise bad_request(f"{name} 取值非法", name, "enum")
    return raw
