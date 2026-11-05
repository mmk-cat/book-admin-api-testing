"""Book create/update/delete tests, including persistence and authorization."""

from __future__ import annotations

from typing import Any

import allure
import pytest

from common.assertions import (
    expect_book_shape,
    expect_error,
    expect_ok,
    expect_status,
)
from common.data_loader import load_data

CASES = load_data("book_write_cases.yaml")
CREATE_VALID = CASES["create_valid"]
CREATE_INVALID = CASES["create_invalid"]
UPDATE_INVALID = CASES["update_invalid"]


def _drop_if_exists(db, isbn: str) -> None:
    row = db.book_by_isbn(isbn)
    if row:
        db.cleanup_book(int(row["id"]))


@allure.epic("图书管理后台接口自动化")
@allure.feature("图书写接口")
class TestBookCreate:
    @allure.story("新增图书")
    @pytest.mark.smoke
    @pytest.mark.book
    @pytest.mark.db
    @pytest.mark.parametrize(
        "case", CREATE_VALID, ids=[item["id"] for item in CREATE_VALID]
    )
    def test_create_book_success(self, admin_api, db, case):
        allure.dynamic.title(f"{case['id']} {case['title']}")
        payload = dict(case["payload"])
        _drop_if_exists(db, payload["isbn"])
        try:
            with allure.step("管理员创建图书"):
                response = admin_api.post("/api/v1/books", json=payload)
            envelope = expect_ok(response, 201)
            book = envelope["data"]
            expect_book_shape(book)
            assert book["isbn"] == payload["isbn"]
            assert book["title"] == payload["title"]
            assert book["stock"] == payload["stock"]
            assert float(book["price"]) == pytest.approx(float(payload["price"]))
            with allure.step("直接查询数据库校验落库结果"):
                row = db.book_by_isbn(payload["isbn"])
                assert row is not None, "接口返回成功但数据库无记录"
                assert int(row["stock"]) == payload["stock"]
                assert float(row["price"]) == pytest.approx(float(payload["price"]))
                assert row["status"] in {"available", "borrowed", "off_shelf"}
                assert row["created_at"] and row["updated_at"]
        finally:
            _drop_if_exists(db, payload["isbn"])

    @allure.story("新增图书异常")
    @pytest.mark.negative
    @pytest.mark.book
    @pytest.mark.parametrize(
        "case", CREATE_INVALID, ids=[item["id"] for item in CREATE_INVALID]
    )
    def test_create_book_invalid(self, admin_api, case):
        allure.dynamic.title(f"{case['id']} {case['title']}")
        response = admin_api.post("/api/v1/books", json=case["payload"])
        expect_error(
            response,
            status=case["status"],
            code=case["code"],
            field=case.get("field"),
        )

    @allure.story("新增图书鉴权")
    @pytest.mark.negative
    @pytest.mark.auth
    @pytest.mark.parametrize(
        "name,client_name,status,code",
        [
            ("未登录", "anonymous_api", 401, 40101),
            ("reader 越权", "reader_api", 403, 40301),
            ("reader2 越权", "reader2_api", 403, 40301),
        ],
    )
    def test_create_book_requires_admin(self, request, name, client_name, status, code):
        allure.dynamic.title(f"BOOK-CREATE-029 新增图书鉴权: {name}")
        client = request.getfixturevalue(client_name)
        response = client.post(
            "/api/v1/books",
            json={
                "isbn": "9787115999999",
                "title": "越权创建",
                "author": "测试",
                "category": "科技",
                "price": 1,
                "stock": 1,
            },
        )
        expect_error(response, status=status, code=code)

    @allure.story("新增图书异常")
    @pytest.mark.negative
    @pytest.mark.db
    def test_create_book_duplicate_isbn(self, admin_api, book_factory):
        allure.dynamic.title("BOOK-CREATE-030 重复 ISBN 提交返回 409 且不产生重复记录")
        book = book_factory()
        response = admin_api.post(
            "/api/v1/books",
            json={
                "isbn": book["isbn"],
                "title": "重复 ISBN",
                "author": "测试",
                "category": "科技",
                "price": 10,
                "stock": 1,
            },
        )
        expect_error(response, status=409, code=40901)

    @allure.story("新增图书落库")
    @pytest.mark.db
    def test_create_book_persists_typed_columns(self, book_factory, db):
        allure.dynamic.title("BOOK-CREATE-031 新增图书后字段类型与审计时间正确")
        book = book_factory(price=12.34, stock=7)
        row = db.book_by_id(book["id"])
        assert row is not None
        assert isinstance(row["stock"], int)
        assert float(row["price"]) == pytest.approx(12.34)
        assert str(row["created_at"])
        assert str(row["updated_at"])


@allure.epic("图书管理后台接口自动化")
@allure.feature("图书写接口")
class TestBookUpdate:
    @allure.story("修改图书")
    @pytest.mark.book
    @pytest.mark.db
    def test_update_book_success(self, admin_api, book_factory, db):
        allure.dynamic.title("BOOK-UPDATE-001 修改图书部分字段并校验落库")
        book = book_factory()
        response = admin_api.put(
            f"/api/v1/books/{book['id']}",
            json={"title": "更新后的标题", "price": 66.6, "stock": 9},
        )
        payload = expect_ok(response)
        updated = payload["data"]
        assert updated["title"] == "更新后的标题"
        assert float(updated["price"]) == pytest.approx(66.6)
        assert updated["stock"] == 9
        row = db.book_by_id(book["id"])
        assert row["title"] == "更新后的标题"
        assert int(row["stock"]) == 9
        assert float(row["price"]) == pytest.approx(66.6)

    @allure.story("修改图书异常")
    @pytest.mark.negative
    @pytest.mark.parametrize(
        "case", UPDATE_INVALID, ids=[item["id"] for item in UPDATE_INVALID]
    )
    def test_update_book_invalid(self, admin_api, book_factory, case):
        allure.dynamic.title(f"{case['id']} {case['title']}")
        book = book_factory()
        response = admin_api.put(f"/api/v1/books/{book['id']}", json=case["payload"])
        expect_error(
            response,
            status=case["status"],
            code=case["code"],
            field=case.get("field"),
        )

    @allure.story("修改图书异常")
    @pytest.mark.negative
    def test_update_book_not_found(self, admin_api):
        allure.dynamic.title("BOOK-UPDATE-008 修改不存在的图书返回 404")
        response = admin_api.put("/api/v1/books/99999", json={"title": "不存在"})
        expect_error(response, status=404, code=40401)

    @allure.story("修改图书鉴权")
    @pytest.mark.negative
    @pytest.mark.auth
    @pytest.mark.parametrize(
        "name,client_name,status,code",
        [
            ("未登录", "anonymous_api", 401, 40101),
            ("reader 越权", "reader_api", 403, 40301),
        ],
    )
    def test_update_book_requires_admin(self, request, book_factory, name, client_name, status, code):
        allure.dynamic.title(f"BOOK-UPDATE-009 修改图书鉴权: {name}")
        book = book_factory()
        client = request.getfixturevalue(client_name)
        response = client.put(f"/api/v1/books/{book['id']}", json={"title": "越权更新"})
        expect_error(response, status=status, code=code)

    @allure.story("修改图书异常")
    @pytest.mark.negative
    def test_update_book_duplicate_isbn(self, admin_api, book_factory):
        allure.dynamic.title("BOOK-UPDATE-010 修改为已存在的 ISBN 返回 409")
        first = book_factory()
        second = book_factory()
        response = admin_api.put(
            f"/api/v1/books/{second['id']}", json={"isbn": first["isbn"]}
        )
        expect_error(response, status=409, code=40901)


@allure.epic("图书管理后台接口自动化")
@allure.feature("图书写接口")
class TestBookDelete:
    @allure.story("删除图书")
    @pytest.mark.book
    @pytest.mark.db
    def test_delete_book_success(self, admin_api, book_factory, db):
        allure.dynamic.title("BOOK-DELETE-001 删除无借阅历史的图书")
        book = book_factory()
        response = admin_api.delete(f"/api/v1/books/{book['id']}")
        payload = expect_ok(response)
        assert payload["data"]["deleted"] == book["id"]
        assert db.book_by_id(book["id"]) is None

    @allure.story("删除图书异常")
    @pytest.mark.negative
    @pytest.mark.db
    def test_delete_book_with_borrow_history(self, admin_api, reader_api, borrow_factory, db):
        allure.dynamic.title("BOOK-DELETE-002 有借阅历史的图书禁止删除")
        context = borrow_factory()
        borrow_id = context["borrow"]["id"]
        returned = reader_api.post(f"/api/v1/borrows/{borrow_id}/return")
        expect_ok(returned)
        response = admin_api.delete(f"/api/v1/books/{context['book']['id']}")
        expect_error(response, status=409, code=40902)
        assert db.book_by_id(context["book"]["id"]) is not None

    @allure.story("删除图书异常")
    @pytest.mark.negative
    def test_delete_book_not_found(self, admin_api):
        allure.dynamic.title("BOOK-DELETE-003 删除不存在的图书返回 404")
        response = admin_api.delete("/api/v1/books/99999")
        expect_error(response, status=404, code=40401)

    @allure.story("删除图书鉴权")
    @pytest.mark.negative
    @pytest.mark.auth
    @pytest.mark.parametrize(
        "name,client_name,status,code",
        [
            ("未登录", "anonymous_api", 401, 40101),
            ("reader 越权", "reader_api", 403, 40301),
        ],
    )
    def test_delete_book_requires_admin(self, request, book_factory, name, client_name, status, code):
        allure.dynamic.title(f"BOOK-DELETE-004 删除图书鉴权: {name}")
        book = book_factory()
        client = request.getfixturevalue(client_name)
        response = client.delete(f"/api/v1/books/{book['id']}")
        expect_error(response, status=status, code=code)
