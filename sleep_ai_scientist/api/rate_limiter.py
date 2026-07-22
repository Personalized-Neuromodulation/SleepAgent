from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable


class RateLimiter:
    def __init__(self, requests_per_second: float = 1.0, enabled: bool = True, sleep_fn: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.time):
        self.requests_per_second = max(float(requests_per_second), 0.001)
        self.enabled = enabled
        self.sleep_fn = sleep_fn
        self.clock = clock
        self.last_call: dict[str, float] = defaultdict(float)

    def wait(self, provider: str) -> None:
        if not self.enabled:
            return
        interval = 1.0 / self.requests_per_second
        now = self.clock()
        elapsed = now - self.last_call[provider]
        if elapsed < interval:
            self.sleep_fn(interval - elapsed)
        self.last_call[provider] = self.clock()
