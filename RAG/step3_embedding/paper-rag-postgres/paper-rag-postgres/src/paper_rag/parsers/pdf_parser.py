from __future__ import annotations

from pathlib import Path

import httpx

from paper_rag.domain import ParsedDocument, ParsedSection
from paper_rag.parsers.base import DocumentParser
from paper_rag.parsers.tei import parse_tei_bytes
from paper_rag.text_utils import normalize_whitespace


class PdfParser(DocumentParser):
    name = "grobid-with-pymupdf-fallback"
    version = "1"

    def __init__(self, grobid_url: str, timeout_seconds: float = 180.0):
        self.grobid_url = grobid_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def parse(self, path: Path) -> ParsedDocument:
        try:
            with path.open("rb") as handle:
                response = httpx.post(
                    f"{self.grobid_url}/api/processFulltextDocument",
                    files={"input": (path.name, handle, "application/pdf")},
                    data={
                        "consolidateHeader": "0",
                        "consolidateCitations": "0",
                        "includeRawCitations": "1",
                        "includeRawAffiliations": "1",
                    },
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            document = parse_tei_bytes(response.content, parser_name="grobid")
            document.parser_version = self.version
            if document.sections:
                return document
        except Exception as exc:
            fallback = self._parse_with_pymupdf(path)
            fallback.warnings.append(f"GROBID不可用或解析失败，已回退PyMuPDF: {exc}")
            return fallback
        return self._parse_with_pymupdf(path)

    def _parse_with_pymupdf(self, path: Path) -> ParsedDocument:
        import fitz

        pages: list[str] = []
        with fitz.open(path) as pdf:
            for page in pdf:
                pages.append(normalize_whitespace(page.get_text("text")))
        nonempty = [page for page in pages if page]
        text = normalize_whitespace("\n\n".join(nonempty))
        if len(text) < 1000:
            raise ValueError("PDF可提取文本过少，可能需要OCR")
        section = ParsedSection(
            title="Full text",
            section_type="other",
            order=0,
            text=text,
            page_start=1,
            page_end=len(pages),
        )
        return ParsedDocument(
            title=path.stem,
            abstract="",
            sections=[section],
            parser_name="pymupdf-fallback",
            parser_version=self.version,
            quality="low",
            warnings=["未恢复章节结构；建议检查GROBID服务或对扫描PDF执行OCR"],
        )

