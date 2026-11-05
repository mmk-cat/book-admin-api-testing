"""Framework self-checks (retry policy, masking, environment config)."""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import allure
import pytest

from common.base_request import BaseRequest
from common.config import load_config
from common.logger import mask_secrets


class _FlakyHandler(BaseHTTPRequestHandler):
    attempts: dict[str, int] = {"GET": 0, "POST": 0}

    def _respond(self, status: int) -> None:
        body = json.dumps({"status": status}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        type(self).attempts["GET"] += 1
        self._respond(503 if type(self).attempts["GET"] < 3 else 200)

    def do_POST(self) -> None:  # noqa: N802
        type(self).attempts["POST"] += 1
        self._respond(503)

    def log_message(self, *_args) -> None:
        return


@pytest.fixture
def flaky_server():
    _FlakyHandler.attempts = {"GET": 0, "POST": 0}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FlakyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", _FlakyHandler
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


@allure.epic("图书管理后台接口自动化")
@allure.feature("测试框架自检")
@pytest.mark.framework
class TestFramework:
    def test_dual_environment_yaml(self):
        allure.dynamic.title("FRAMEWORK-001 YAML 双环境配置可加载且数据库后端不同")
        dev = load_config("dev")
        test = load_config("test")
        assert dev.env == "dev" and test.env == "test"
        assert dev.db["backend"] == "sqlite"
        assert test.db["backend"] == "mysql"
        assert dev.base_url.startswith("http://")
        assert test.base_url.startswith("http://")
        assert dev.users["admin"]["username"] == "admin"

    def test_get_retries_on_503(self, test_config, flaky_server):
        allure.dynamic.title("FRAMEWORK-002 GET 对 503 自动重试并最终成功")
        base_url, handler = flaky_server
        config = replace(test_config, base_url=base_url)
        client = BaseRequest(config, retries=2)
        try:
            response = client.get("/flaky", auth=False)
        finally:
            client.close()
        assert response.status_code == 200
        assert handler.attempts["GET"] == 3, "total=2 应产生 1 次原始请求 + 2 次重试"

    def test_post_is_not_retried(self, test_config, flaky_server):
        allure.dynamic.title("FRAMEWORK-003 POST 不自动重试，避免重复写数据")
        base_url, handler = flaky_server
        config = replace(test_config, base_url=base_url)
        client = BaseRequest(config, retries=2)
        try:
            response = client.post("/write", auth=False, json={"x": 1})
        finally:
            client.close()
        assert response.status_code == 503
        assert handler.attempts["POST"] == 1

    def test_secret_masking(self):
        allure.dynamic.title("FRAMEWORK-004 日志中的 Token 与密码被脱敏")
        raw = 'Authorization: Bearer abc.def.ghi {"password": "admin123", "access_token": "xyz"}'
        masked = mask_secrets(raw)
        assert "abc.def.ghi" not in masked
        assert "admin123" not in masked
        assert "xyz" not in masked
        assert "***" in masked
