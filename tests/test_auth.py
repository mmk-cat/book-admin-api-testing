"""Authentication, Token lifecycle and logout tests."""

from __future__ import annotations

import allure
import pytest

from common.assertions import body, expect_error, expect_ok, expect_status
from common.data_loader import load_data
from common.token_tools import (
    expired_token,
    forged_token,
    make_token,
    token_claims,
)

CASES = load_data("auth_cases.yaml")
LOGIN_POSITIVE = CASES["login_positive"]
LOGIN_NEGATIVE = CASES["login_negative"]


@allure.epic("图书管理后台接口自动化")
@allure.feature("认证接口")
class TestAuthentication:
    @allure.story("登录")
    @pytest.mark.smoke
    @pytest.mark.parametrize(
        "case", LOGIN_POSITIVE, ids=[item["id"] for item in LOGIN_POSITIVE]
    )
    def test_login_success(self, anonymous_api, test_config, case):
        allure.dynamic.title(f"{case['id']} {case['title']}")
        with allure.step("POST /api/v1/auth/login"):
            response = anonymous_api.post(
                "/api/v1/auth/login",
                auth=False,
                json={"username": case["username"], "password": case["password"]},
            )
        payload = expect_ok(response)
        data = payload["data"]
        assert data["token_type"] == "Bearer"
        assert data["user"]["username"] == case["username"]
        assert data["user"]["role"] == case["role"]
        assert data["expires_in"] == test_config.token_ttl_seconds
        claims = token_claims(data["access_token"])
        assert claims["sub"] == data["user"]["id"]
        assert claims["role"] == case["role"]
        assert claims["exp"] - claims["iat"] == test_config.token_ttl_seconds
        assert response.headers["X-Request-ID"] == payload["request_id"]

    @allure.story("登录异常")
    @pytest.mark.negative
    @pytest.mark.parametrize(
        "case", LOGIN_NEGATIVE, ids=[item["id"] for item in LOGIN_NEGATIVE]
    )
    def test_login_negative(self, anonymous_api, case):
        allure.dynamic.title(f"{case['id']} {case['title']}")
        with allure.step(f"提交异常登录数据: {case['title']}"):
            response = anonymous_api.post(
                "/api/v1/auth/login", auth=False, json=case["payload"]
            )
        expect_error(
            response,
            status=case["status"],
            code=case["code"],
            field=case.get("field"),
        )

    @allure.story("登录异常")
    def test_login_body_must_be_json_object(self, anonymous_api):
        allure.dynamic.title("AUTH-LOGIN-016 登录请求体必须是 JSON 对象")
        response = anonymous_api.post(
            "/api/v1/auth/login", auth=False, json=["admin", "admin123"]
        )
        expect_error(response, status=400, code=40001, reason="invalid_json")

    @allure.story("登录异常")
    def test_login_requires_json_content_type(self, anonymous_api):
        allure.dynamic.title("AUTH-LOGIN-017 非 JSON Content-Type 被拒绝")
        response = anonymous_api.post(
            "/api/v1/auth/login",
            auth=False,
            data={"username": "admin", "password": "admin123"},
        )
        expect_error(response, status=400, code=40001)

    @allure.story("当前用户")
    def test_me_success(self, reader_api):
        allure.dynamic.title("AUTH-ME-001 使用有效 Token 获取当前用户")
        response = reader_api.get("/api/v1/auth/me")
        payload = expect_ok(response)
        assert payload["data"]["username"] == "reader"
        assert payload["data"]["role"] == "reader"
        assert payload["data"]["status"] == "active"

    @allure.story("当前用户")
    @pytest.mark.negative
    @pytest.mark.parametrize(
        "name,headers,status,code",
        [
            ("缺少 Authorization", {}, 401, 40101),
            ("认证方案错误", {"Authorization": "Token abc"}, 401, 40102),
            ("Token 格式错误", {"Authorization": "Bearer v1.bad"}, 401, 40103),
        ],
        ids=["no-header", "wrong-scheme", "malformed-token"],
    )
    def test_me_header_errors(self, anonymous_api, name, headers, status, code):
        allure.dynamic.title(f"AUTH-ME-002 获取当前用户: {name}")
        response = anonymous_api.get("/api/v1/auth/me", auth=False, headers=headers)
        expect_error(response, status=status, code=code)

    @allure.story("当前用户")
    @pytest.mark.negative
    @pytest.mark.parametrize(
        "name,token_kind",
        [("签名被篡改", "forged"), ("Token 已过期", "expired")],
        ids=["forged-signature", "expired-token"],
    )
    def test_me_token_signature_and_expiry(self, anonymous_api, test_config, name, token_kind):
        allure.dynamic.title(f"AUTH-ME-003 获取当前用户: {name}")
        token = (
            forged_token(test_config.token_secret)
            if token_kind == "forged"
            else expired_token(test_config.token_secret)
        )
        response = anonymous_api.get(
            "/api/v1/auth/me",
            auth=False,
            headers={"Authorization": f"Bearer {token}"},
        )
        expect_error(response, status=401, code=40103)

    @allure.story("当前用户")
    @pytest.mark.negative
    def test_me_token_with_unknown_user(self, anonymous_api, test_config):
        allure.dynamic.title("AUTH-ME-004 Token 合法但用户不存在")
        token = make_token(
            user_id=9999,
            username="ghost",
            role="reader",
            secret=test_config.token_secret,
            jti="unknown-user",
        )
        response = anonymous_api.get(
            "/api/v1/auth/me",
            auth=False,
            headers={"Authorization": f"Bearer {token}"},
        )
        expect_error(response, status=401, code=40105)

    @allure.story("登出")
    def test_logout_revokes_token(self, anonymous_api, test_config):
        allure.dynamic.title("AUTH-LOGOUT-001 登出后原 Token 立即失效")
        login = anonymous_api.post(
            "/api/v1/auth/login",
            auth=False,
            json={"username": "reader", "password": "reader123"},
        )
        token = expect_ok(login)["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        logout = anonymous_api.post("/api/v1/auth/logout", auth=False, headers=headers)
        expect_ok(logout)
        replay = anonymous_api.post("/api/v1/auth/logout", auth=False, headers=headers)
        expect_error(replay, status=401, code=40104)
        me = anonymous_api.get("/api/v1/auth/me", auth=False, headers=headers)
        expect_error(me, status=401, code=40104)

    @allure.story("登出")
    @pytest.mark.negative
    def test_logout_requires_token(self, anonymous_api):
        allure.dynamic.title("AUTH-LOGOUT-002 未登录调用登出返回 401")
        response = anonymous_api.post("/api/v1/auth/logout", auth=False)
        expect_error(response, status=401, code=40101)
