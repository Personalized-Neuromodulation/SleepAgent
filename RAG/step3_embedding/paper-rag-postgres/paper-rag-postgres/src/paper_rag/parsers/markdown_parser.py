from __future__ import annotations

import re
from pathlib import Path

from paper_rag.domain import ParsedDocument, ParsedSection
from paper_rag.parsers.base import DocumentParser
from paper_rag.text_utils import normalize_section_type, normalize_whitespace


class MarkdownParser(DocumentParser):
    name = "markdown-headings"
    version = "1"

    def parse(self, path: Path) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
        if raw.startswith("---\n"):
            closing = raw.find("\n---", 4)
            if closing != -1:
                raw = raw[closing + 4 :]
        heading_pattern = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
        matches = list(heading_pattern.finditer(raw))
        title = path.stem
        sections: list[ParsedSection] = []

        for index, match in enumerate(matches):
            heading = normalize_whitespace(match.group(2).strip("# "))
            if len(match.group(1)) == 1 and title == path.stem:
                title = heading
                continue
            end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
            body = self._clean_markdown(raw[match.end() : end])
            if body:
                sections.append(
                    ParsedSection(
                        title=heading,
                        section_type=normalize_section_type(heading),
                        order=len(sections),
                        text=body,
                    )
                )

        if not sections:
            text = self._clean_markdown(raw)
            if text:
                sections.append(ParsedSection("Full text", "other", 0, text))
        total_text = sum(len(section.text) for section in sections)
        if total_text < 500:
            raise ValueError("Markdown中没有足够的论文全文")
        abstract = next(
            (section.text for section in sections if section.section_type == "abstract"), ""
        )
        return ParsedDocument(
            title=title,
            abstract=abstract,
            sections=sections,
            parser_name=self.name,
            parser_version=self.version,
            quality="medium" if len(sections) >= 3 else "low",
            warnings=[] if matches else ["Markdown未识别到章节标题"],
        )

    @staticmethod
    def _clean_markdown(text: str) -> str:
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        text = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[*_`~]+", "", text)
        return normalize_whitespace(text)
