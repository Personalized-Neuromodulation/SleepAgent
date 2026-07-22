from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from sleep_ai_scientist.api.cache import APICache
from sleep_ai_scientist.api.rate_limiter import RateLimiter
from sleep_ai_scientist.schemas.api import APICallLog


class BaseAPIClient:
    def __init__(
        self,
        provider: str,
        base_url: str,
        timeout_seconds: float = 20,
        max_retries: int = 3,
        backoff_seconds: float = 1.5,
        cache: APICache | None = None,
        rate_limiter: RateLimiter | None = None,
        session: Any | None = None,
        fail_open: bool = True,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.cache = cache
        self.rate_limiter = rate_limiter or RateLimiter(enabled=False)
        self.session = session or requests.Session()
        self.fail_open = fail_open
        self.logs: list[APICallLog] = []

    def get(self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, query: str | None = None) -> dict[str, Any]:
        params = params or {}
        cached = self.cache.get(self.provider, endpoint, params) if self.cache else None
        if cached is not None:
            self.logs.append(self._log(endpoint, query, None, True, 0.0, True, None))
            return cached
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_error: Exception | None = None
        start = time.time()
        for attempt in range(max(1, self.max_retries)):
            try:
                self.rate_limiter.wait(self.provider)
                response = self.session.get(url, params=params, headers=headers or {}, timeout=self.timeout_seconds)
                elapsed = time.time() - start
                response.raise_for_status()
                payload = response.json()
                if self.cache:
                    self.cache.set(self.provider, endpoint, params, payload)
                self.logs.append(self._log(endpoint, query, response.status_code, True, elapsed, False, None))
                return payload
            except Exception as exc:  # requests can raise several concrete exception types.
                last_error = exc
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_seconds * (attempt + 1))
        elapsed = time.time() - start
        self.logs.append(self._log(endpoint, query, None, False, elapsed, False, str(last_error)))
        if self.fail_open:
            return {}
        raise RuntimeError(f"{self.provider} API call failed: {last_error}") from last_error

    def _log(self, endpoint: str, query: str | None, status_code: int | None, success: bool, elapsed: float | None, cached: bool, error: str | None) -> APICallLog:
        return APICallLog(
            provider=self.provider,
            endpoint=endpoint,
            query=query,
            status_code=status_code,
            success=success,
            elapsed_seconds=round(elapsed, 4) if elapsed is not None else None,
            cached=cached,
            error=error,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
