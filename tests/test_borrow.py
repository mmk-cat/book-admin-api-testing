"""Borrow / return workflows, stock consistency and borrow-list scope."""

from __future__ import annotations

from datetime import datetime, timezone

import allure
import pytest

from common.assertions import expect_error, expect_ok, expect_status
from common.data_loader import load_data

BORROW_INVALID = load_data("borrow_cases.yaml")["borrow_invalid"]


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@allure.epic("图书管理后台接口自动化")
@allure.feature("借阅接口")
class TestBorrow:
    @allure.story("借书")
    @pytest.mark.smoke
    @pytest.mark.borrow
    @pytest.mark.db
    def test_borrow_success(self, reader_api, book_factory, db):
        allure.dynamic.title("BORROW-001 读者借书成功，库存与借阅记录同时落库")
        book = book_factory(stock=3)
        response = reader_api.post(
            f"/api/v1/books/{book['id']}/borrow", json={"quantity": 2}
        )
        payload = expect_ok(response, 201)
        record = payload["data"]
        assert record["book_id"] == book["id"]
        assert record["user_id"] == 2
        assert record["quantity"] == 2
        assert record["status"] == "borrowed"
        assert 29 <= (_dt(record["due_at"]) - _dt(record["borrowed_at"])).days <= 30
        db_book = db.book_by_id(book["id"])
        assert int(db_book["stock"]) == 1
        db_borrow = db.query_one("SELECT * FROM borrows WHERE id = ?", (record["id"],))
        assert db_borrow["status"] == "borrowed"
        assert int(db_borrow["quantity"]) == 2
        assert db_borrow["returned_at"] is None

    @allure.story("借书异常")
    @pytest.mark.negative
    @pytest.mark.borrow
    @pytest.mark.parametrize(
        "case", BORROW_INVALID, ids=[item["id"] for item in BORROW_INVALID]
    )
    def test_borrow_invalid(self, reader_api, book_factory, db, case):
        allure.dynamic.title(f"{case['id']} {case['title']}")
        if case["target"] == "fresh":
            book_id = book_factory(stock=3)["id"]
        elif case["target"] == "off_shelf":
            book_id = 5
        elif case["target"] == "out_of_stock":
            book_id = 6
        else:
            book_id = 99999
        response = reader_api.post(
            f"/api/v1/books/{book_id}/borrow", json=case["payload"]
        )
        expect_error(
            response,
            status=case["status"],
            code=case["code"],
            field=case.get("field"),
        )

    @allure.story("借书异常")
    @pytest.mark.negative
    @pytest.mark.borrow
    @pytest.mark.db
    def test_borrow_insufficient_stock_is_atomic(self, reader_api, book_factory, db):
        allure.dynamic.title("BORROW-010 库存不足时借阅失败且库存不变")
        book = book_factory(stock=3)
        response = reader_api.post(
            f"/api/v1/books/{book['id']}/borrow", json={"quantity": 4}
        )
        expect_error(response, status=409, code=40904)
        row = db.book_by_id(book["id"])
        assert int(row["stock"]) == 3
        count = db.scalar("SELECT COUNT(*) FROM borrows WHERE book_id = ?", (book["id"],))
        assert int(count) == 0

    @allure.story("借书鉴权")
    @pytest.mark.negative
    @pytest.mark.auth
    @pytest.mark.parametrize(
        "name,client_name,status,code",
        [("未登录", "anonymous_api", 401, 40101), ("管理员不允许借阅", "admin_api", 403, 40301)],
    )
    def test_borrow_requires_reader(self, request, book_factory, name, client_name, status, code):
        allure.dynamic.title(f"BORROW-011 借书鉴权: {name}")
        book = book_factory()
        client = request.getfixturevalue(client_name)
        response = client.post(f"/api/v1/books/{book['id']}/borrow", json={"quantity": 1})
        expect_error(response, status=status, code=code)


@allure.epic("图书管理后台接口自动化")
@allure.feature("借阅接口")
class TestReturn:
    @allure.story("还书")
    @pytest.mark.borrow
    @pytest.mark.db
    def test_return_success(self, reader_api, borrow_factory, db):
        allure.dynamic.title("RETURN-001 读者还书成功，库存恢复且记录关闭")
        context = borrow_factory(quantity=2)
        borrow_id = context["borrow"]["id"]
        response = reader_api.post(f"/api/v1/borrows/{borrow_id}/return")
        payload = expect_ok(response)
        record = payload["data"]
        assert record["status"] == "returned"
        assert record["returned_at"]
        db_book = db.book_by_id(context["book"]["id"])
        assert int(db_book["stock"]) == 3
        db_borrow = db.query_one("SELECT * FROM borrows WHERE id = ?", (borrow_id,))
        assert db_borrow["status"] == "returned"
        assert db_borrow["returned_at"]

    @allure.story("还书异常")
    @pytest.mark.negative
    def test_return_twice_conflict(self, reader_api, borrow_factory):
        allure.dynamic.title("RETURN-002 重复归还同一借阅返回 409")
        context = borrow_factory()
        borrow_id = context["borrow"]["id"]
        expect_ok(reader_api.post(f"/api/v1/borrows/{borrow_id}/return"))
        response = reader_api.post(f"/api/v1/borrows/{borrow_id}/return")
        expect_error(response, status=409, code=40905)

    @allure.story("还书鉴权")
    @pytest.mark.negative
    @pytest.mark.auth
    def test_return_other_users_borrow_forbidden(self, reader2_api, borrow_factory, db):
        allure.dynamic.title("RETURN-003 读者不能归还他人的借阅")
        context = borrow_factory()
        borrow_id = context["borrow"]["id"]
        response = reader2_api.post(f"/api/v1/borrows/{borrow_id}/return")
        expect_error(response, status=403, code=40303)
        row = db.query_one("SELECT status FROM borrows WHERE id = ?", (borrow_id,))
        assert row["status"] == "borrowed"

    @allure.story("还书异常")
    @pytest.mark.negative
    def test_return_not_found(self, reader_api):
        allure.dynamic.title("RETURN-004 归还不存在的借阅返回 404")
        response = reader_api.post("/api/v1/borrows/99999/return")
        expect_error(response, status=404, code=40402)

    @allure.story("还书鉴权")
    @pytest.mark.negative
    def test_return_requires_auth(self, anonymous_api, borrow_factory):
        allure.dynamic.title("RETURN-005 未登录归还借阅返回 401")
        context = borrow_factory()
        response = anonymous_api.post(
            f"/api/v1/borrows/{context['borrow']['id']}/return", auth=False
        )
        expect_error(response, status=401, code=40101)

    @allure.story("还书")
    @pytest.mark.borrow
    def test_admin_can_return(self, admin_api, borrow_factory):
        allure.dynamic.title("RETURN-006 管理员可代读者归还")
        context = borrow_factory()
        response = admin_api.post(f"/api/v1/borrows/{context['borrow']['id']}/return")
        payload = expect_ok(response)
        assert payload["data"]["status"] == "returned"


@allure.epic("图书管理后台接口自动化")
@allure.feature("借阅接口")
class TestBorrowList:
    @allure.story("借阅列表")
    @pytest.mark.borrow
    @pytest.mark.db
    def test_reader_only_sees_own_borrows(self, reader_api, reader2_api, borrow_factory, db):
        allure.dynamic.title("BORROW-LIST-001 读者列表只返回本人借阅")
        borrow_factory(api=reader_api)
        borrow_factory(api=reader2_api)
        response = reader_api.get("/api/v1/borrows", params={"page_size": 50})
        payload = expect_ok(response)
        items = payload["data"]["items"]
        assert all(item["user_id"] == 2 for item in items)
        expected = int(
            db.scalar("SELECT COUNT(*) FROM borrows WHERE user_id = ?", (2,))
        )
        assert payload["data"]["pagination"]["total"] == expected

    @allure.story("借阅列表")
    @pytest.mark.borrow
    @pytest.mark.db
    def test_admin_sees_all_borrows(self, admin_api, borrow_factory, db):
        allure.dynamic.title("BORROW-LIST-002 管理员列表返回全量借阅")
        borrow_factory()
        response = admin_api.get("/api/v1/borrows", params={"page_size": 50})
        payload = expect_ok(response)
        assert payload["data"]["pagination"]["total"] == int(
            db.scalar("SELECT COUNT(*) FROM borrows")
        )
        for item in payload["data"]["items"]:
            assert item["book_title"]
            assert item["username"]

    @allure.story("借阅列表")
    @pytest.mark.borrow
    @pytest.mark.db
    def test_filter_by_status(self, reader_api, borrow_factory, db):
        allure.dynamic.title("BORROW-LIST-003 按 borrowed/returned 状态过滤")
        active = borrow_factory()
        returned = borrow_factory()
        expect_ok(reader_api.post(f"/api/v1/borrows/{returned['borrow']['id']}/return"))
        for status in ("borrowed", "returned"):
            response = reader_api.get(
                "/api/v1/borrows", params={"status": status, "page_size": 50}
            )
            payload = expect_ok(response)
            assert all(item["status"] == status for item in payload["data"]["items"])
            expected = int(
                db.scalar(
                    "SELECT COUNT(*) FROM borrows WHERE user_id = ? AND status = ?",
                    (2, status),
                )
            )
            assert payload["data"]["pagination"]["total"] == expected
        assert active["borrow"]["id"] != returned["borrow"]["id"]

    @allure.story("借阅列表")
    @pytest.mark.negative
    def test_invalid_status(self, reader_api):
        allure.dynamic.title("BORROW-LIST-004 非法状态枚举返回 400")
        response = reader_api.get("/api/v1/borrows", params={"status": "lost"})
        expect_error(response, status=400, code=40001)

    @allure.story("借阅列表")
    @pytest.mark.borrow
    def test_pagination(self, reader_api, borrow_factory):
        allure.dynamic.title("BORROW-LIST-005 借阅列表分页元数据正确")
        borrow_factory()
        borrow_factory()
        first = expect_ok(
            reader_api.get("/api/v1/borrows", params={"page": 1, "page_size": 1})
        )
        second = expect_ok(
            reader_api.get("/api/v1/borrows", params={"page": 2, "page_size": 1})
        )
        assert len(first["data"]["items"]) == 1
        assert len(second["data"]["items"]) == 1
        assert second["data"]["pagination"]["page"] == 2
        assert first["data"]["items"][0]["id"] != second["data"]["items"][0]["id"]

    @allure.story("借阅列表")
    @pytest.mark.negative
    @pytest.mark.auth
    def test_requires_auth(self, anonymous_api):
        allure.dynamic.title("BORROW-LIST-006 未登录查看借阅列表返回 401")
        response = anonymous_api.get("/api/v1/borrows", auth=False)
        expect_error(response, status=401, code=40101)
