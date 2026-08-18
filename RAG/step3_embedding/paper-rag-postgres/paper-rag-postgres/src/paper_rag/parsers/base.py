from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from paper_rag.domain import ParsedDocument


class DocumentParser(ABC):
    name = "base"
    version = "1"

    @abstractmethod
    def parse(self, path: Path) -> ParsedDocument:
        raise NotImplementedError

