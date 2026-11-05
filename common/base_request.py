"""Thin requests wrapper shared by every test module.

Responsibilities:
* unified Token authentication (login once per role);
* one Session per client with connection pooling;
* timeouts, bounded retries for idempotent requests only;
* masked request/response logging and request-id tracing.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import TestConfig
from .logger import get_logger, mask_secrets


class BaseRequest:
    def __init__(
        self,
        config: TestConfig,
        *,
        role: str | None = None,
        token: str | None = None,
        retries: int | None = None,
    ) -> None:
        self.config = config
        self.role = role
        self.token = token
        self.logger = get_logger(config.project_root / "logs" / "api_tests.log")
        retry = Retry(
            total=config.retries if retries is None else retries,
            connect=config.retries if retries is None else retries,
            read=0,
            status=config.retries if retries is None else retries,
            backoff_factor=config.backoff_factor,
            status_forcelist=(502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
            respect_retry_after_header=False,
            raise_on_status=False,
        )
        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.last_exchange: dict[str, Any] | None = None

    # ------------------------------------------------------------------ auth
    def login(self) -> str:
        if not self.role or self.role not in self.config.users:
            raise RuntimeError(f"No credentials configured for role '{self.role}'")
        credentials = self.config.users[self.role]
        response = self._request(
            "POST",
            "/api/v1/auth/login",
            auth=False,
            json={"username": credentials["username"], "password": credentials["password"]},
        )
        if response.status_code != 200:
            raise RuntimeError(f"Login failed for {self.role}: {response.status_code} {response.text}")
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Login failed for {self.role}: {payload}")
        self.token = payload["data"]["access_token"]
        return self.token

    def ensure_token(self) -> str:
        if not self.token:
            return self.login()
        return self.token

    # ------------------------------------------------------------------ HTTP verbs
    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", path, **kwargs)

    def request(self, method: str, path: str, *, auth: bool = True, **kwargs: Any) -> requests.Response:
        return self._request(method, path, auth=auth, **kwargs)

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        url = path if path.startswith(("http://", "https://")) else f"{self.config.base_url}{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        request_id = headers.get("X-Request-ID") or uuid.uuid4().hex[:20]
        headers.setdefault("X-Request-ID", request_id)
        headers.setdefault("Accept", "application/json")
        if auth and (self.token or self.role):
            headers.setdefault("Authorization", f"Bearer {self.ensure_token()}")
        timeout = kwargs.pop("timeout", self.config.timeout)

        started = time.perf_counter()
        try:
            response = self.session.request(
                method, url, headers=headers, timeout=timeout, **kwargs
            )
        except requests.RequestException as exc:
            self.logger.error(
                "REQUEST %s %s -> EXCEPTION %s (%.0fms) rid=%s",
                method, url, exc, (time.perf_counter() - started) * 1000, request_id,
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.elapsed_ms = elapsed_ms  # type: ignore[attr-defined]
        exchange = {
            "request": {
                "method": method,
                "url": url,
                "headers": mask_secrets(json.dumps(headers, ensure_ascii=False)),
                "body": mask_secrets(
                    json.dumps(kwargs.get("json"), ensure_ascii=False)
                    if kwargs.get("json") is not None
                    else str(kwargs.get("data", ""))
                ),
                "request_id": request_id,
            },
            "response": {
                "status": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        }
        self.last_exchange = exchange
        self.logger.info(
            "%s %s -> %s %.0fms rid=%s",
            method, url, response.status_code, elapsed_ms, request_id,
        )
        return response

    def close(self) -> None:
        self.session.close()
