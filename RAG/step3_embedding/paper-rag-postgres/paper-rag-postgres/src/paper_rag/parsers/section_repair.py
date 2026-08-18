from __future__ import annotations

import re

from paper_rag.domain import ParsedSection
from paper_rag.text_utils import normalize_section_type, normalize_whitespace


MAJOR_SECTION_TYPES = {
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "conclusion",
    "data_availability",
    "references",
}


def _is_short_label_section(section: ParsedSection) -> bool:
    title = normalize_whitespace(section.title)
    if len(title) > 12:
        return False
    return bool(re.fullmatch(r"[A-Za-z]{1,6}\d+[A-Za-z]?", title))


def _is_definition_context(section: ParsedSection) -> bool:
    title = normalize_whitespace(section.title).lower()
    text = normalize_whitespace(section.text)
    if text.endswith(":"):
        return True
    return any(term in title for term in ("comparison", "labelling", "labeling", "naming", "convention"))


def repair_flat_section_hierarchy(sections: list[ParsedSection]) -> list[ParsedSection]:
    repaired: list[ParsedSection] = []
    current_major_title: str | None = None
    current_major_type: str | None = None

    for section in sections:
        title_type = normalize_section_type(section.title)
        if section.parent_title is None and section.section_type in MAJOR_SECTION_TYPES and title_type != "other":
            section.section_type = title_type
            current_major_title = section.title
            current_major_type = section.section_type
            repaired.append(section)
            continue

        if section.parent_title is None and section.section_type == "other" and current_major_type:
            if _is_short_label_section(section) and repaired and _is_definition_context(repaired[-1]):
                repaired[-1].text = normalize_whitespace(f"{repaired[-1].text}\n\n{section.title}: {section.text}")
                continue
            section.section_type = current_major_type
            section.parent_title = current_major_title

        repaired.append(section)

    for order, section in enumerate(repaired):
        section.order = order
    return repaired
