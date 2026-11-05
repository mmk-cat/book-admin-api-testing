"""Shared pytest fixtures for the Book Admin API suite."""

from __future__ import annotations

import itertools
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
import requests

from common.base_request import BaseRequest
from common.config import PROJECT_ROOT, TestConfig, load_config
from common.db_client import DBClient
from common.token_tools import token_for_admin

REPORTS_DIR = PROJECT_ROOT / "reports"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--env",
        action="store",
        default=None,
        help="config/config.yaml environment name (dev/test)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "smoke: 核心冒烟用例")
    config.addinivalue_line("markers", "negative: 逆向/异常用例")
    config.addinivalue_line("markers", "auth: 认证与鉴权")
    config.addinivalue_line("markers", "book: 图书接口")
    config.addinivalue_line("markers", "borrow: 借阅接口")
    config.addinivalue_line("markers", "contract: 响应契约")
    config.addinivalue_line("markers", "db: 落库校验")
    config.addinivalue_line("markers", "framework: 框架自检（不计入接口用例统计）")


@pytest.fixture(scope="session")
def test_config(request: pytest.FixtureRequest) -> TestConfig:
    config = load_config(request.config.getoption("--env"))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    allure_dir = REPORTS_DIR / "allure-results"
    allure_dir.mkdir(parents=True, exist_ok=True)
    (allure_dir / "environment.properties").write_text(
        "\n".join(
            [
                f"Environment={config.env}",
                f"Base.URL={config.base_url}",
                f"DB.Backend={config.db['backend']}",
                f"Python={platform.python_version()}",
                f"OS={platform.platform()}",
                f"Tester=Zheng Shuang",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def _health_url(config: TestConfig) -> str:
    return f"{config.base_url}{config.health_path}"


def _is_healthy(config: TestConfig, timeout: float = 0.7) -> bool:
    try:
        response = requests.get(_health_url(config), timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _tail(path: Path, lines: int = 80) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
    except OSError:
        return "<server log unavailable>"


@pytest.fixture(scope="session", autouse=True)
def api_server(test_config: TestConfig):
    own_process: subprocess.Popen | None = None
    if _is_healthy(test_config):
        yield {"mode": "external", "base_url": test_config.base_url}
        return
    if not test_config.auto_start:
        pytest.fail(
            f"{test_config.base_url} 不可用，且当前环境未开启 auto_start。"
            " 请先启动服务或使用 --env dev。"
        )
    if test_config.db["backend"] != "sqlite":
        pytest.fail("auto_start 仅支持 SQLite 演示环境；MySQL 环境请先启动服务")

    sqlite_path = test_config.sqlite_path
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(sqlite_path) + suffix)
        if candidate.exists():
            candidate.unlink()

    parsed = urlparse(test_config.base_url)
    port = parsed.port or 5001
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex((parsed.hostname or "127.0.0.1", port)) == 0:
            pytest.fail(f"端口 {port} 已被占用，但 {test_config.base_url} 健康检查失败")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = REPORTS_DIR / "server.log"
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(PROJECT_ROOT / "backend"),
            "PYTHONUNBUFFERED": "1",
            "DB_BACKEND": "sqlite",
            "SQLITE_PATH": str(sqlite_path),
            "TOKEN_SECRET": test_config.token_secret,
            "APP_HOST": parsed.hostname or "127.0.0.1",
            "APP_PORT": str(port),
        }
    )
    log_file = log_path.open("w", encoding="utf-8")
    own_process = subprocess.Popen(
        [sys.executable, "-m", "book_admin.run"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + test_config.startup_timeout_seconds
    while time.time() < deadline:
        if own_process.poll() is not None:
            log_file.close()
            pytest.fail(f"Demo API 启动失败:\n{_tail(log_path)}")
        if _is_healthy(test_config):
            break
        time.sleep(0.2)
    else:
        own_process.terminate()
        log_file.close()
        pytest.fail(f"Demo API 启动超时:\n{_tail(log_path)}")

    yield {"mode": "owned", "base_url": test_config.base_url, "pid": own_process.pid}
    if own_process.poll() is None:
        own_process.terminate()
        try:
            own_process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            own_process.kill()
            own_process.wait(timeout=5)
    log_file.close()


@pytest.fixture(scope="session")
def db(test_config: TestConfig, api_server) -> DBClient:
    return DBClient(test_config)


@pytest.fixture(scope="session")
def admin_api(test_config: TestConfig, api_server) -> BaseRequest:
    client = BaseRequest(test_config, role="admin")
    client.login()
    yield client
    client.close()


@pytest.fixture(scope="session")
def reader_api(test_config: TestConfig, api_server) -> BaseRequest:
    client = BaseRequest(test_config, role="reader")
    client.login()
    yield client
    client.close()


@pytest.fixture(scope="session")
def reader2_api(test_config: TestConfig, api_server) -> BaseRequest:
    client = BaseRequest(test_config, role="reader2")
    client.login()
    yield client
    client.close()


@pytest.fixture(scope="session")
def anonymous_api(test_config: TestConfig, api_server) -> BaseRequest:
    client = BaseRequest(test_config)
    yield client
    client.close()


@pytest.fixture(scope="session")
def custom_admin_token(test_config: TestConfig) -> str:
    return token_for_admin(test_config.token_secret)


@pytest.fixture
def book_factory(admin_api: BaseRequest, db: DBClient):
    counter = itertools.count(1)
    created: list[int] = []

    def create(**overrides: Any) -> dict[str, Any]:
        sequence = next(counter)
        suffix = str(int(time.time_ns()) % 10_000_000 + sequence).zfill(7)
        payload = {
            "isbn": f"978{suffix}{sequence:03d}",
            "title": f"接口测试图书-{sequence}",
            "author": "测试作者",
            "category": "科技",
            "price": 39.9,
            "stock": 3,
        }
        payload.update(overrides)
        response = admin_api.post("/api/v1/books", json=payload)
        if response.status_code != 201:
            pytest.fail(
                f"创建测试图书失败: HTTP {response.status_code} {response.text}\npayload={payload}"
            )
        data = response.json()["data"]
        created.append(int(data["id"]))
        return data

    yield create
    for book_id in reversed(created):
        db.cleanup_book(book_id)


@pytest.fixture
def borrow_factory(reader_api: BaseRequest, book_factory):
    def create(
        *,
        book: dict[str, Any] | None = None,
        quantity: int = 1,
        api: BaseRequest | None = None,
    ) -> dict[str, Any]:
        book = book or book_factory(stock=max(3, quantity))
        response = (api or reader_api).post(
            f"/api/v1/books/{book['id']}/borrow", json={"quantity": quantity}
        )
        if response.status_code != 201:
            pytest.fail(f"创建测试借阅失败: HTTP {response.status_code} {response.text}")
        return {"book": book, "borrow": response.json()["data"], "response": response}

    return create
