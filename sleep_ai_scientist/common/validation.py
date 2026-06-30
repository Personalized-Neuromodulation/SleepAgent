from __future__ import annotations

from pathlib import Path


def require_file(path: Path) -> Path:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    return path
