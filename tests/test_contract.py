"""Statistics, response contract, observability and DB schema checks."""

from __future__ import annotations

import re

import allure
import pytest

from common.assertions import expect_error, expect_ok, expect_status


@allure.epic("图书管理后台接口自动化")
@allure.feature("统计与契约")
class TestStats:
    @allure.story("运营概览")
    @pytest.mark.smoke
    @pytest.mark.db
    def test_stats_matches_database(self, admin_api, db):
        allure.dynamic.title("STATS-001 管理端概览与数据库聚合结果一致")
        response = admin_api.get("/api/v1/stats/overview")
        payload = expect_ok(response)
        stats = payload["data"]
        expected_books = db.query_one(
            "SELECT COUNT(*) AS total_books, COALESCE(SUM(stock), 0) AS total_stock, "
            "COALESCE(SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END), 0) AS available_books "
            "FROM books"
        )
        assert stats["total_books"] == int(expected_books["total_books"])
        assert stats["total_stock"] == int(expected_books["total_stock"])
        assert stats["available_books"] == int(expected_books["available_books"])
        assert stats["total_users"] == int(db.scalar("SELECT COUNT(*) FROM users"))
        assert stats["active_borrows"] == int(
            db.scalar("SELECT COUNT(*) FROM borrows WHERE status = 'borrowed'")
        )
        assert stats["overdue_borrows"] >= 0
        assert isinstance(stats["top_categories"], list) and stats["top_categories"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stats["generated_at"])

    @allure.story("运营概览")
    @pytest.mark.negative
    @pytest.mark.auth
    def test_stats_forbidden_for_reader(self, reader_api):
        allure.dynamic.title("STATS-002 reader 越权访问运营概览返回 403")
        response = reader_api.get("/api/v1/stats/overview")
        expect_error(response, status=403, code=40301)

    @allure.story("运营概览")
    @pytest.mark.negative
    @pytest.mark.auth
    def test_stats_requires_auth(self, anonymous_api):
        allure.dynamic.title("STATS-003 未登录访问运营概览返回 401")
        response = anonymous_api.get("/api/v1/stats/overview", auth=False)
        expect_error(response, status=401, code=40101)


@allure.epic("图书管理后台接口自动化")
@allure.feature("统计与契约")
class TestContract:
    @allure.story("统一响应")
    def test_success_envelope_contract(self, admin_api):
        allure.dynamic.title("CONTRACT-002 成功响应统一包含 code/message/data/request_id")
        response = admin_api.get("/api/v1/books/1")
        expect_status(response, 200)
        payload = response.json()
        assert set(payload) == {"code", "message", "data", "request_id"}
        assert payload["code"] == 0
        assert payload["message"] == "ok"
        assert response.headers["Content-Type"].startswith("application/json")
        assert float(response.headers["X-Process-Time-Ms"]) >= 0

    @allure.story("统一响应")
    @pytest.mark.negative
    def test_error_envelope_contract(self, admin_api):
        allure.dynamic.title("CONTRACT-003 错误响应包含稳定业务码与请求 ID")
        response = admin_api.get("/api/v1/books/99999")
        payload = expect_error(response, status=404, code=40401)
        assert payload["data"] is None
        assert payload["request_id"] == response.headers["X-Request-ID"]

    @allure.story("请求追踪")
    def test_custom_request_id_is_echoed(self, admin_api):
        allure.dynamic.title("CONTRACT-004 合法 X-Request-ID 原样回传")
        request_id = "req-contract-2026"
        response = admin_api.get(
            "/api/v1/books/1", headers={"X-Request-ID": request_id}
        )
        payload = expect_ok(response)
        assert payload["request_id"] == request_id
        assert response.headers["X-Request-ID"] == request_id

    @allure.story("请求追踪")
    def test_invalid_request_id_is_replaced(self, admin_api):
        allure.dynamic.title("CONTRACT-005 非法 X-Request-ID 由服务端重新生成")
        response = admin_api.get(
            "/api/v1/books/1", headers={"X-Request-ID": "bad id with spaces"}
        )
        payload = expect_ok(response)
        assert payload["request_id"] != "bad id with spaces"
        assert re.fullmatch(r"[0-9a-f]{32}", payload["request_id"])

    @allure.story("统一响应")
    @pytest.mark.negative
    def test_method_not_allowed(self, admin_api):
        allure.dynamic.title("CONTRACT-006 不支持的 HTTP 方法返回 JSON 405")
        response = admin_api.post("/api/v1/stats/overview", json={})
        payload = expect_error(response, status=405, code=40500)
        assert payload["request_id"]

    @allure.story("数据库约束")
    @pytest.mark.db
    def test_book_column_types(self, db, test_config):
        allure.dynamic.title("CONTRACT-007 books 表关键字段类型符合预期")
        columns = {name.lower(): value for name, value in db.column_types("books").items()}
        if test_config.db["backend"] == "sqlite":
            assert columns["price"].startswith("NUMERIC")
            assert columns["stock"] == "INTEGER"
            assert columns["isbn"].startswith("VARCHAR")
        else:
            assert columns["price"].startswith("decimal(10,2)")
            assert columns["stock"].startswith("int")
            assert columns["isbn"].startswith("varchar(20)")

    @allure.story("健康检查")
    def test_health_endpoint(self, anonymous_api):
        allure.dynamic.title("CONTRACT-008 服务健康检查可用")
        response = anonymous_api.get("/healthz", auth=False)
        expect_status(response, 200)
        assert response.json()["status"] == "ok"
        assert response.json()["db_backend"] in {"sqlite", "mysql"}


class TestDatabaseSchema:
    @allure.story("数据库约束")
    @pytest.mark.db
    def test_unique_indexes_exist(self, db):
        allure.dynamic.title("CONTRACT-009 用户与图书 ISBN 唯一约束生效")
        assert db.scalar("SELECT COUNT(*) FROM users WHERE username = 'admin'") == 1
        assert db.scalar("SELECT COUNT(*) FROM books WHERE isbn = '9787115000001'") == 1
