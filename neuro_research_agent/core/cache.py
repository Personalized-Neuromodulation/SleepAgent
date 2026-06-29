from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .io import read_json, write_json


class JsonCache:
    def __init__(self, root: Path):
        self.root = root

    def key_path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return self.root / namespace / f"{digest}.json"

    def get(self, namespace: str, key: str) -> Any | None:
        path = self.key_path(namespace, key)
        if not path.exists():
            return None
        return read_json(path)

    def set(self, namespace: str, key: str, value: Any) -> Path:
        path = self.key_path(namespace, key)
        write_json(path, value)
        return path

