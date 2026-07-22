from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry_call(fn: Callable[[], T], max_retries: int = 3, backoff_seconds: float = 1.5) -> T:
    last_error: Exception | None = None
    for attempt in range(max(1, max_retries)):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(backoff_seconds * (attempt + 1))
    raise RuntimeError(last_error)
