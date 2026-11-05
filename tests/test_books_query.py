"""Book list/detail query contract, pagination and filter tests."""

from __future__ import annotations

from typing import Any

import allure
import pytest

from common.assertions import (
    expect_book_shape,
    expect_error,
    expect_ok,
    expect_pagination,
)
from common.data_loader import load_data

CASES = load_data("book_query_cases.yaml")
POSITIVE = CASES["list_positive"]
INVALID = CASES["list_invalid"]


def _expected_total(db, query: dict[str, Any]) -> int:
    where = ["1 = 1"]
    params: list[Any] = []
    if query.get("category"):
        where.append("category = ?")
        params.append(query["category"])
    if query.get("status"):
        where.append("status = ?")
        params.append(query["status"])
    if query.get("keyword"):
        like = f"%{query['keyword']}%"
        where.append("(title LIKE ? OR author LIKE ? OR isbn LIKE ?)")
        params.extend([like, like, like])
    row = db.query_one(f"SELECT COUNT(*) AS total FROM books WHERE {' AND '.join(where)}", params)
    return int(row["total"])


@allure.epic("图书管理后台接口自动化")
@allure.feature("图书查询接口")
class TestBookQuery:
    @allure.story("图书列表")
    @pytest.mark.smoke
    @pytest.mark.book
    @pytest.mark.parametrize("case", POSITIVE, ids=[item["id"] for item in POSITIVE])
    def test_list_books(self, admin_api, db, case):
        allure.dynamic.title(f"{case['id']} {case['title']}")
        query = case["query"]
        with allure.step(f"GET /api/v1/books params={query}"):
            response = admin_api.get("/api/v1/books", params=query)
        payload = expect_ok(response)
        page = case["page"]
        page_size = case["page_size"]
        expect_pagination(payload, page=page, page_size=page_size)
        data = payload["data"]
        items = data["items"]
        total = data["pagination"]["total"]
        assert total == _expected_total(db, query), "分页 total 与数据库 COUNT 不一致"
        expected_len = 0 if case.get("empty") else min(page_size, max(0, total - (page - 1) * page_size))
        assert len(items) == expected_len
        for book in items:
            expect_book_shape(book)
            if query.get("category"):
                assert book["category"] == query["category"]
            if query.get("status"):
                assert book["status"] == query["status"]
            if query.get("keyword"):
                needle = str(query["keyword"]).lower()
                haystack = f"{book['title']} {book['author']} {book['isbn']}".lower()
                assert needle in haystack
        if query.get("sort") == "price":
            prices = [float(book["price"]) for book in items]
            assert prices == sorted(prices, reverse=query.get("order") == "desc")
        if query.get("sort") == "stock":
            stocks = [int(book["stock"]) for book in items]
            assert stocks == sorted(stocks, reverse=query.get("order") == "desc")

    @allure.story("图书列表")
    @pytest.mark.negative
    @pytest.mark.book
    @pytest.mark.parametrize("case", INVALID, ids=[item["id"] for item in INVALID])
    def test_list_books_invalid_query(self, admin_api, case):
        allure.dynamic.title(f"{case['id']} {case['title']}")
        response = admin_api.get("/api/v1/books", params=case["query"])
        expect_error(response, status=case["status"], code=case["code"])

    @allure.story("图书列表")
    @pytest.mark.negative
    @pytest.mark.auth
    @pytest.mark.parametrize(
        "name,headers",
        [("缺少 Token", {}), ("Token 格式错误", {"Authorization": "Bearer broken.token"})],
        ids=["missing-token", "malformed-token"],
    )
    def test_list_books_requires_auth(self, anonymous_api, name, headers):
        allure.dynamic.title(f"BOOK-LIST-025 图书列表鉴权: {name}")
        response = anonymous_api.get("/api/v1/books", auth=False, headers=headers)
        expect_error(response, status=401, code=40101 if not headers else 40103)

    @allure.story("图书详情")
    def test_get_book_success(self, admin_api):
        allure.dynamic.title("BOOK-GET-001 查询存在的图书详情")
        response = admin_api.get("/api/v1/books/1")
        payload = expect_ok(response)
        expect_book_shape(payload["data"])
        assert payload["data"]["id"] == 1

    @allure.story("图书详情")
    @pytest.mark.negative
    @pytest.mark.parametrize("book_id", [99999, 0], ids=["not-exist", "zero-id"])
    def test_get_book_not_found(self, admin_api, book_id):
        allure.dynamic.title(f"BOOK-GET-002 查询不存在图书 id={book_id}")
        response = admin_api.get(f"/api/v1/books/{book_id}")
        expect_error(response, status=404, code=40401)

    @allure.story("图书详情")
    @pytest.mark.negative
    def test_get_book_non_integer_id(self, admin_api):
        allure.dynamic.title("BOOK-GET-003 非整数图书 id 路由不匹配")
        response = admin_api.get("/api/v1/books/abc")
        expect_error(response, status=404, code=40400)

    @allure.story("图书列表")
    @pytest.mark.negative
    def test_keyword_sql_injection_is_safe(self, admin_api):
        allure.dynamic.title("BOOK-LIST-026 关键字 SQL 注入被参数化查询阻断")
        response = admin_api.get(
            "/api/v1/books", params={"keyword": "' OR 1=1 --", "page_size": 50}
        )
        payload = expect_ok(response)
        assert payload["data"]["pagination"]["total"] == 0

    @allure.story("未知路由")
    def test_unknown_route_returns_json(self, admin_api):
        allure.dynamic.title("CONTRACT-001 未知路由返回统一 JSON 404")
        response = admin_api.get("/api/v1/not-a-real-route")
        payload = expect_error(response, status=404, code=40400)
        assert payload["request_id"]
        assert response.headers["Content-Type"].startswith("application/json")
