from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paper_rag.domain import ParsedAsset, ParsedDocument, ParsedSection
from paper_rag.parsers.base import DocumentParser
from paper_rag.text_utils import normalize_section_type, normalize_whitespace


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return normalize_whitespace(value)
    if isinstance(value, list):
        return normalize_whitespace("\n\n".join(_text(item) for item in value if item is not None))
    if isinstance(value, dict):
        for key in ("text", "content", "body", "value"):
            if key in value:
                return _text(value[key])
    return normalize_whitespace(str(value))


class JsonParser(DocumentParser):
    """Parse a canonical/full-text JSON object without assuming one publisher schema."""

    name = "json-flexible"
    version = "1"

    def parse(self, path: Path) -> ParsedDocument:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, list):
            payload = {"sections": payload}
        if not isinstance(payload, dict):
            raise ValueError("JSON全文根节点必须是对象或章节数组")

        title = _text(payload.get("title") or payload.get("article_title")) or path.stem
        abstract = _text(payload.get("abstract") or payload.get("summary"))
        raw_sections = payload.get("sections") or payload.get("body_sections") or []
        sections: list[ParsedSection] = []

        if isinstance(raw_sections, dict):
            raw_sections = [
                {"title": heading, "text": content}
                for heading, content in raw_sections.items()
            ]
        if isinstance(raw_sections, list):
            for item in raw_sections:
                if isinstance(item, str):
                    section_title, body = "Untitled section", _text(item)
                    metadata: dict[str, Any] = {}
                elif isinstance(item, dict):
                    section_title = _text(
                        item.get("title") or item.get("heading") or item.get("section")
                    ) or "Untitled section"
                    body = _text(item.get("text") or item.get("content") or item.get("body"))
                    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                else:
                    continue
                if body:
                    sections.append(
                        ParsedSection(
                            title=section_title,
                            section_type=normalize_section_type(section_title),
                            order=len(sections),
                            text=body,
                            page_start=item.get("page_start") if isinstance(item, dict) else None,
                            page_end=item.get("page_end") if isinstance(item, dict) else None,
                            metadata=metadata,
                        )
                    )

        if not sections:
            full_text = _text(
                payload.get("full_text")
                or payload.get("fulltext")
                or payload.get("content")
                or payload.get("text")
                or payload.get("body")
            )
            if full_text:
                sections.append(ParsedSection("Full text", "other", 0, full_text))

        if abstract and not any(section.section_type == "abstract" for section in sections):
            sections.insert(0, ParsedSection("Abstract", "abstract", 0, abstract))
            for order, section in enumerate(sections):
                section.order = order

        total_text = sum(len(section.text) for section in sections)
        if total_text < 500:
            raise ValueError("JSON中没有足够的论文全文，可能只有元数据")

        assets: list[ParsedAsset] = []
        for asset_type, key in (("figure", "figures"), ("table", "tables")):
            values = payload.get(key) or []
            if isinstance(values, list):
                for index, item in enumerate(values, start=1):
                    if not isinstance(item, dict):
                        continue
                    caption = _text(item.get("caption") or item.get("title"))
                    content = _text(item.get("content") or item.get("text"))
                    if caption or content:
                        assets.append(
                            ParsedAsset(
                                asset_type,
                                _text(item.get("label")) or f"{asset_type.title()} {index}",
                                caption,
                                page=item.get("page"),
                                content=content or None,
                            )
                        )

        authors = payload.get("authors") or []
        if isinstance(authors, str):
            authors = [value.strip() for value in authors.split(",") if value.strip()]
        references = payload.get("references") or []
        if not isinstance(references, list):
            references = []
        return ParsedDocument(
            title=title,
            abstract=abstract,
            sections=sections,
            assets=assets,
            references=[_text(item) for item in references if _text(item)],
            parser_name=self.name,
            parser_version=self.version,
            quality="high" if len(sections) >= 4 and total_text >= 5_000 else "medium",
            metadata={
                "authors": authors if isinstance(authors, list) else [],
                "publication_date": payload.get("publication_date") or payload.get("date") or "",
            },
        )
