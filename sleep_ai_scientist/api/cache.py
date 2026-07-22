from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import ensure_parent


class APICache:
    def __init__(self, cache_dir: str | Path, enabled: bool = True):
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled

    def key(self, provider: str, endpoint: str, params: dict[str, Any]) -> str:
        payload = json.dumps({"provider": provider, "endpoint": endpoint, "params": params}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def path_for(self, provider: str, endpoint: str, params: dict[str, Any]) -> Path:
        return self.cache_dir / provider / f"{self.key(provider, endpoint, params)}.json"

    def get(self, provider: str, endpoint: str, params: dict[str, Any]) -> Any | None:
        if not self.enabled:
            return None
        path = self.path_for(provider, endpoint, params)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, provider: str, endpoint: str, params: dict[str, Any], payload: Any) -> None:
        if not self.enabled:
            return
        path = self.path_for(provider, endpoint, params)
        ensure_parent(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
