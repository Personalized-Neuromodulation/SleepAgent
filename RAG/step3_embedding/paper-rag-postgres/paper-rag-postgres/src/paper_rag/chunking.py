from __future__ import annotations

import re
from collections.abc import Callable
from uuid import UUID

from paper_rag.domain import Chunk, ParsedDocument, ParsedSection
from paper_rag.text_utils import normalize_whitespace, sha256_text


def approximate_token_count(text: str) -> int:
    # English scientific text is usually ~1.3 tokens/word; CJK characters are counted directly.
    words = len(re.findall(r"[A-Za-z0-9_]+", text))
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    punctuation = len(re.findall(r"[^\w\s]", text))
    return max(1, int(words * 1.3 + cjk + punctuation * 0.2))


def _paragraphs(text: str) -> list[str]:
    values = [normalize_whitespace(value) for value in re.split(r"\n\s*\n", text)]
    return [value for value in values if value]


def _split_long_text(text: str, max_tokens: int, counter: Callable[[str], int]) -> list[str]:
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    parts: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        trial = " ".join([*current, sentence]).strip()
        if current and counter(trial) > max_tokens:
            parts.append(" ".join(current))
            current = [sentence]
        else:
            current.append(sentence)
    if current:
        parts.append(" ".join(current))
    return parts


def _pack(
    paragraphs: list[str],
    max_tokens: int,
    overlap_tokens: int,
    counter: Callable[[str], int],
) -> list[str]:
    expanded: list[str] = []
    for paragraph in paragraphs:
        if counter(paragraph) > max_tokens:
            expanded.extend(_split_long_text(paragraph, max_tokens, counter))
        else:
            expanded.append(paragraph)

    chunks: list[str] = []
    current: list[str] = []
    for paragraph in expanded:
        trial = "\n\n".join([*current, paragraph])
        if current and counter(trial) > max_tokens:
            chunks.append("\n\n".join(current))
            overlap: list[str] = []
            for previous in reversed(current):
                if counter("\n\n".join(reversed([previous, *overlap]))) > overlap_tokens:
                    break
                overlap.insert(0, previous)
            current = [*overlap, paragraph]
        else:
            current.append(paragraph)
    if current:
        chunks.append("\n\n".join(current))
    return [normalize_whitespace(chunk) for chunk in chunks if normalize_whitespace(chunk)]


class HierarchicalChunker:
    version = "hierarchical-v1"

    def __init__(
        self,
        parent_tokens: int = 1200,
        child_tokens: int = 550,
        child_overlap: int = 80,
        token_counter: Callable[[str], int] = approximate_token_count,
    ):
        if child_tokens >= parent_tokens:
            raise ValueError("child_tokens必须小于parent_tokens")
        self.parent_tokens = parent_tokens
        self.child_tokens = child_tokens
        self.child_overlap = child_overlap
        self.token_counter = token_counter

    def chunk(self, document: ParsedDocument) -> list[Chunk]:
        chunks: list[Chunk] = []
        for section in document.sections:
            chunks.extend(self._chunk_section(section))
        for asset_index, asset in enumerate(document.assets):
            text = normalize_whitespace(
                f"{asset.asset_type.title()} {asset.label}\n{asset.caption}\n{asset.content or ''}"
            )
            if text:
                chunks.append(
                    Chunk.new(
                        section_order=10_000 + asset_index,
                        level="child",
                        index=asset_index,
                        text=text,
                        token_count=self.token_counter(text),
                        text_hash=sha256_text(text),
                        section_type=f"{asset.asset_type}_caption",
                        section_title=asset.label,
                        page_start=asset.page,
                        page_end=asset.page,
                        metadata={"asset": True},
                    )
                )
        return chunks

    def _chunk_section(self, section: ParsedSection) -> list[Chunk]:
        parents = _pack(_paragraphs(section.text), self.parent_tokens, 0, self.token_counter)
        output: list[Chunk] = []
        child_index = 0
        for parent_index, parent_text in enumerate(parents):
            parent = Chunk.new(
                section_order=section.order,
                level="parent",
                index=parent_index,
                text=parent_text,
                token_count=self.token_counter(parent_text),
                text_hash=sha256_text(parent_text),
                section_type=section.section_type,
                section_title=section.title,
                page_start=section.page_start,
                page_end=section.page_end,
            )
            output.append(parent)
            children = _pack(
                _paragraphs(parent_text),
                self.child_tokens,
                self.child_overlap,
                self.token_counter,
            )
            for child_text in children:
                output.append(
                    Chunk.new(
                        section_order=section.order,
                        level="child",
                        index=child_index,
                        text=child_text,
                        token_count=self.token_counter(child_text),
                        text_hash=sha256_text(child_text),
                        section_type=section.section_type,
                        section_title=section.title,
                        page_start=section.page_start,
                        page_end=section.page_end,
                        parent_chunk_id=parent.chunk_id,
                    )
                )
                child_index += 1
        return output


def embedding_text(paper_title: str, chunk: Chunk) -> str:
    return normalize_whitespace(
        f"Paper: {paper_title}\nSection: {chunk.section_type}\n"
        f"Heading: {chunk.section_title}\nText: {chunk.text}"
    )

