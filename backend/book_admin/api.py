"""Book Admin HTTP API (12 business endpoints)."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, current_app, g, jsonify, request

from .security import (
    ApiError,
    TokenError,
    decode_token,
    make_token,
    token_expiry_datetime,
    token_fingerprint,
    verify_password,
)
from .validators import (
    BOOK_STATUSES,
    BORROW_STATUSES,
    CATEGORIES,
    SORT_FIELDS,
    SORT_ORDERS,
    bad_request,
    parse_book_payload,
    parse_enum,
    parse_int,
    query_enum,
    query_int,
    require_fields,
    require_json_object,
)

api = Blueprint("api", __name__, url_prefix="/api/v1")


# --------------------------------------------------------------------------- helpers
def db():
    return current_app.extensions["db"]


def settings():
    return current_app.extensions["settings"]


def _request_id() -> str:
    return getattr(g, "request_id", "")


def ok(data: Any = None, status: int = 200):
    return (
        jsonify(
            {
                "code": 0,
                "message": "ok",
                "data": data,
                "request_id": _request_id(),
            }
        ),
        status,
    )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat().replace("+00:00", "Z")
    text = str(value)
    if len(text) == 19 and text[4] == "-" and text[10] == " ":
        return text.replace(" ", "T") + "Z"
    return text


def serialize_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "role": row["role"],
        "status": row["status"],
        "created_at": _iso(row["created_at"]),
    }


def serialize_book(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "isbn": row["isbn"],
        "title": row["title"],
        "author": row["author"],
        "category": row["category"],
        "price": float(row["price"]),
        "stock": int(row["stock"]),
        "status": row["status"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def serialize_borrow(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "book_id": int(row["book_id"]),
        "book_title": row.get("book_title"),
        "user_id": int(row["user_id"]),
        "username": row.get("username"),
        "quantity": int(row["quantity"]),
        "status": row["status"],
        "borrowed_at": _iso(row["borrowed_at"]),
        "due_at": _iso(row["due_at"]),
        "returned_at": _iso(row["returned_at"]),
    }


def _book_row(book_id: int) -> dict[str, Any]:
    row = db().query_one("SELECT * FROM books WHERE id = ?", (book_id,))
    if row is None:
        raise ApiError(404, 40401, "图书不存在")
    return row


def _borrow_row(borrow_id: int) -> dict[str, Any]:
    row = db().query_one(
        "SELECT b.*, bk.title AS book_title, u.username "
        "FROM borrows b JOIN books bk ON bk.id = b.book_id "
        "JOIN users u ON u.id = b.user_id WHERE b.id = ?",
        (borrow_id,),
    )
    if row is None:
        raise ApiError(404, 40402, "借阅记录不存在")
    return row


def _duplicate_isbn(exc: Exception) -> bool:
    text = str(exc).lower()
    return isinstance(exc, sqlite3.IntegrityError) or "duplicate" in text or "unique" in text


def auth_required(*roles: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            header = request.headers.get("Authorization", "")
            if not header:
                raise ApiError(401, 40101, "未提供访问令牌")
            parts = header.split()
            if len(parts) != 2 or parts[0].lower() != "bearer":
                raise ApiError(401, 40102, "Authorization 格式应为 Bearer <token>")
            token = parts[1]
            try:
                payload = decode_token(token, settings().token_secret)
            except TokenError as exc:
                raise ApiError(401, 40103, f"访问令牌无效: {exc}") from exc
            fingerprint = token_fingerprint(token)
            revoked = db().query_one(
                "SELECT token_hash FROM auth_tokens WHERE token_hash = ?", (fingerprint,)
            )
            if revoked:
                raise ApiError(401, 40104, "访问令牌已注销")
            user = db().query_one("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),))
            if user is None:
                raise ApiError(401, 40105, "令牌对应用户不存在")
            if user["status"] != "active":
                raise ApiError(403, 40302, "用户已被禁用")
            if roles and user["role"] not in roles:
                raise ApiError(403, 40301, "无权执行该操作")
            g.user = user
            g.token_payload = payload
            g.token_fingerprint = fingerprint
            g.access_token = token
            return func(*args, **kwargs)

        return wrapper

    return decorator


# --------------------------------------------------------------------------- auth: 3
@api.post("/auth/login")
def login():
    data = require_json_object()
    # Reuse strict string validation but keep password whitespace untouched.
    from .validators import parse_str

    require_fields(data, ("username", "password"))
    username = parse_str(data, "username", max_len=50)
    password = parse_str(data, "password", max_len=128, strip=False)
    user = db().query_one("SELECT * FROM users WHERE username = ?", (username,))
    if user is None or not verify_password(password, user["password_hash"]):
        raise ApiError(401, 40110, "用户名或密码错误")
    if user["status"] != "active":
        raise ApiError(403, 40302, "账号已被禁用")
    token = make_token(user, settings().token_secret, settings().token_ttl_seconds)
    return ok(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": settings().token_ttl_seconds,
            "user": serialize_user(user),
        }
    )


@api.post("/auth/logout")
@auth_required()
def logout():
    payload = g.token_payload
    expires_at = token_expiry_datetime(payload).strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if settings().db_backend == "mysql":
        db().execute(
            "INSERT INTO auth_tokens (token_hash, expires_at, created_at) VALUES (?, ?, ?) "
            "ON DUPLICATE KEY UPDATE expires_at = VALUES(expires_at)",
            (g.token_fingerprint, expires_at, now),
        )
    else:
        db().execute(
            "INSERT OR REPLACE INTO auth_tokens (token_hash, expires_at, created_at) "
            "VALUES (?, ?, ?)",
            (g.token_fingerprint, expires_at, now),
        )
    return ok({"logged_out": True})


@api.get("/auth/me")
@auth_required()
def me():
    return ok(serialize_user(g.user))


# --------------------------------------------------------------------------- books: 5
@api.get("/books")
@auth_required()
def list_books():
    page = query_int("page", 1, minimum=1, maximum=100_000)
    page_size = query_int("page_size", 10, minimum=1, maximum=50)
    category = query_enum("category", CATEGORIES)
    status = query_enum("status", BOOK_STATUSES)
    keyword = request.args.get("keyword", "").strip()
    if len(keyword) > 50:
        raise bad_request("keyword 长度不能超过 50", "keyword", "max_length")
    sort = request.args.get("sort", "created_at").lower()
    order = request.args.get("order", "desc").lower()
    if sort not in SORT_FIELDS:
        raise bad_request("sort 取值非法", "sort", "enum")
    if order not in SORT_ORDERS:
        raise bad_request("order 取值非法", "order", "enum")

    where = ["1 = 1"]
    params: list[Any] = []
    if category:
        where.append("category = ?")
        params.append(category)
    if status:
        where.append("status = ?")
        params.append(status)
    if keyword:
        where.append("(title LIKE ? OR author LIKE ? OR isbn LIKE ?)")
        like = f"%{keyword}%"
        params.extend([like, like, like])
    where_sql = " AND ".join(where)
    total_row = db().query_one(f"SELECT COUNT(*) AS total FROM books WHERE {where_sql}", params)
    total = int(total_row["total"] if total_row else 0)
    offset = (page - 1) * page_size
    rows = db().query_all(
        f"SELECT * FROM books WHERE {where_sql} "
        f"ORDER BY {sort} {order.upper()}, id ASC LIMIT ? OFFSET ?",
        [*params, page_size, offset],
    )
    return ok(
        {
            "items": [serialize_book(row) for row in rows],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": math.ceil(total / page_size) if total else 0,
            },
        }
    )


@api.get("/books/<int:book_id>")
@auth_required()
def get_book(book_id: int):
    return ok(serialize_book(_book_row(book_id)))


@api.post("/books")
@auth_required("admin")
def create_book():
    data = require_json_object()
    payload = parse_book_payload(data)
    if db().query_one("SELECT id FROM books WHERE isbn = ?", (payload["isbn"],)):
        raise ApiError(409, 40901, "isbn 已存在")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    status = payload.get("status", "available")
    try:
        result = db().execute(
            "INSERT INTO books (isbn, title, author, category, price, stock, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload["isbn"],
                payload["title"],
                payload["author"],
                payload["category"],
                payload["price"],
                payload["stock"],
                status,
                now,
                now,
            ),
        )
    except Exception as exc:  # race-safe duplicate handling
        if _duplicate_isbn(exc):
            raise ApiError(409, 40901, "isbn 已存在") from exc
        raise
    row = db().query_one("SELECT * FROM books WHERE id = ?", (result["lastrowid"],))
    return ok(serialize_book(row), 201)


@api.put("/books/<int:book_id>")
@auth_required("admin")
def update_book(book_id: int):
    existing = _book_row(book_id)
    data = require_json_object()
    payload = parse_book_payload(data, partial=True)
    if "isbn" in payload and payload["isbn"] != existing["isbn"]:
        duplicate = db().query_one(
            "SELECT id FROM books WHERE isbn = ? AND id <> ?", (payload["isbn"], book_id)
        )
        if duplicate:
            raise ApiError(409, 40901, "isbn 已存在")
    assignments = [f"{column} = ?" for column in payload]
    values = list(payload.values())
    assignments.append("updated_at = ?")
    values.append(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    values.append(book_id)
    db().execute(f"UPDATE books SET {', '.join(assignments)} WHERE id = ?", values)
    return ok(serialize_book(_book_row(book_id)))


@api.delete("/books/<int:book_id>")
@auth_required("admin")
def delete_book(book_id: int):
    _book_row(book_id)
    history = db().query_one(
        "SELECT COUNT(*) AS total FROM borrows WHERE book_id = ?",
        (book_id,),
    )
    if history and int(history["total"]) > 0:
        raise ApiError(409, 40902, "图书存在借阅记录，不能删除")
    db().execute("DELETE FROM books WHERE id = ?", (book_id,))
    return ok({"deleted": book_id})


# --------------------------------------------------------------------------- borrow: 4
@api.post("/books/<int:book_id>/borrow")
@auth_required("reader")
def borrow_book(book_id: int):
    book = _book_row(book_id)
    raw_body = request.get_data(cache=True)
    data: dict[str, Any] = {}
    if raw_body:
        data = require_json_object()
    quantity = parse_int(data, "quantity", minimum=1, maximum=5, default=1)
    if book["status"] == "off_shelf":
        raise ApiError(409, 40903, "图书已下架")
    if int(book["stock"]) < quantity:
        raise ApiError(409, 40904, "库存不足")
    now_dt = datetime.now(timezone.utc)
    now = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    due = (now_dt + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    user_id = int(g.user["id"])
    with db().transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            db()._sql(
                "UPDATE books SET stock = stock - ?, "
                "status = CASE WHEN stock - ? = 0 THEN 'borrowed' ELSE status END, "
                "updated_at = ? WHERE id = ? AND status <> 'off_shelf' AND stock >= ?"
            ),
            (quantity, quantity, now, book_id, quantity),
        )
        if cursor.rowcount != 1:
            raise ApiError(409, 40904, "库存不足或图书状态已变化")
        cursor.execute(
            db()._sql(
                "INSERT INTO borrows (book_id, user_id, quantity, status, borrowed_at, due_at) "
                "VALUES (?, ?, ?, 'borrowed', ?, ?)"
            ),
            (book_id, user_id, quantity, now, due),
        )
        borrow_id = cursor.lastrowid
    return ok(serialize_borrow(_borrow_row(int(borrow_id))), 201)


@api.post("/borrows/<int:borrow_id>/return")
@auth_required()
def return_book(borrow_id: int):
    borrow = _borrow_row(borrow_id)
    if g.user["role"] != "admin" and int(borrow["user_id"]) != int(g.user["id"]):
        raise ApiError(403, 40303, "只能归还本人的借阅")
    if borrow["status"] == "returned":
        raise ApiError(409, 40905, "该借阅已归还")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with db().transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            db()._sql(
                "UPDATE borrows SET status = 'returned', returned_at = ? "
                "WHERE id = ? AND status = 'borrowed'"
            ),
            (now, borrow_id),
        )
        if cursor.rowcount != 1:
            raise ApiError(409, 40905, "该借阅已归还")
        cursor.execute(
            db()._sql(
                "UPDATE books SET stock = stock + ?, "
                "status = CASE WHEN status = 'borrowed' THEN 'available' ELSE status END, "
                "updated_at = ? WHERE id = ?"
            ),
            (int(borrow["quantity"]), now, int(borrow["book_id"])),
        )
    return ok(serialize_borrow(_borrow_row(borrow_id)))


@api.get("/borrows")
@auth_required()
def list_borrows():
    page = query_int("page", 1, minimum=1, maximum=100_000)
    page_size = query_int("page_size", 10, minimum=1, maximum=50)
    status = query_enum("status", BORROW_STATUSES)
    where = ["1 = 1"]
    params: list[Any] = []
    if g.user["role"] != "admin":
        where.append("b.user_id = ?")
        params.append(int(g.user["id"]))
    if status:
        where.append("b.status = ?")
        params.append(status)
    where_sql = " AND ".join(where)
    total_row = db().query_one(
        f"SELECT COUNT(*) AS total FROM borrows b WHERE {where_sql}", params
    )
    total = int(total_row["total"] if total_row else 0)
    rows = db().query_all(
        "SELECT b.*, bk.title AS book_title, u.username FROM borrows b "
        "JOIN books bk ON bk.id = b.book_id JOIN users u ON u.id = b.user_id "
        f"WHERE {where_sql} ORDER BY b.id DESC LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    )
    return ok(
        {
            "items": [serialize_borrow(row) for row in rows],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": math.ceil(total / page_size) if total else 0,
            },
        }
    )


@api.get("/stats/overview")
@auth_required("admin")
def stats_overview():
    books = db().query_one(
        "SELECT COUNT(*) AS total_books, COALESCE(SUM(stock), 0) AS total_stock, "
        "COALESCE(SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END), 0) AS available_books "
        "FROM books"
    )
    users = db().query_one("SELECT COUNT(*) AS total_users FROM users")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    borrows = db().query_one(
        "SELECT COUNT(*) AS active_borrows, "
        "COALESCE(SUM(CASE WHEN due_at < ? THEN 1 ELSE 0 END), 0) AS overdue_borrows "
        "FROM borrows WHERE status = 'borrowed'",
        (now,),
    )
    categories = db().query_all(
        "SELECT category, COUNT(*) AS book_count, COALESCE(SUM(stock), 0) AS stock "
        "FROM books GROUP BY category ORDER BY book_count DESC, category ASC"
    )
    return ok(
        {
            "total_books": int(books["total_books"]),
            "available_books": int(books["available_books"]),
            "total_stock": int(books["total_stock"]),
            "total_users": int(users["total_users"]),
            "active_borrows": int(borrows["active_borrows"]),
            "overdue_borrows": int(borrows["overdue_borrows"]),
            "top_categories": [
                {
                    "category": row["category"],
                    "book_count": int(row["book_count"]),
                    "stock": int(row["stock"]),
                }
                for row in categories
            ],
            "generated_at": _iso(now),
        }
    )
