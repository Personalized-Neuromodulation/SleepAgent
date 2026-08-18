from __future__ import annotations

from pathlib import Path

from paper_rag.parsers.base import DocumentParser
from paper_rag.parsers.pdf_parser import PdfParser
from paper_rag.parsers.json_parser import JsonParser
from paper_rag.parsers.markdown_parser import MarkdownParser
from paper_rag.parsers.xml_parser import XmlParser


class ParserRegistry:
    def __init__(self, grobid_url: str, timeout_seconds: float = 180.0):
        self.parsers: dict[str, DocumentParser] = {
            "application/pdf": PdfParser(grobid_url, timeout_seconds),
            "application/xml": XmlParser(),
            "application/json": JsonParser(),
            "text/markdown": MarkdownParser(),
        }

    def get(self, path: Path, mime_type: str | None = None) -> DocumentParser:
        suffix_mimes = {
            ".pdf": "application/pdf",
            ".xml": "application/xml",
            ".json": "application/json",
            ".md": "text/markdown",
            ".markdown": "text/markdown",
        }
        parser = self.parsers.get(mime_type or suffix_mimes.get(path.suffix.lower(), ""))
        if parser is None:
            raise ValueError(f"不支持的文件格式: {mime_type or path.suffix}")
        return parser
