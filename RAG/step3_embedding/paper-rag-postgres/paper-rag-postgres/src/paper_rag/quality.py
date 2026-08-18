from __future__ import annotations

from paper_rag.domain import ParsedDocument


def assess_parsed_document(document: ParsedDocument) -> list[str]:
    """Apply inexpensive safeguards before an extracted document reaches RAG."""
    warnings: list[str] = []
    total_text = sum(len(section.text) for section in document.sections)
    if total_text < 1_000:
        warnings.append("可用正文少于1000字符")
    if not document.abstract:
        warnings.append("未解析到摘要")
    if len(document.sections) < 3:
        warnings.append("章节数少于3，可能未恢复论文结构")
    if not any(section.section_type in {"methods", "results"} for section in document.sections):
        warnings.append("未识别到Methods或Results章节")
    unique_hashes = {section.text.strip() for section in document.sections if section.text.strip()}
    if len(unique_hashes) != len([section for section in document.sections if section.text.strip()]):
        warnings.append("解析结果包含重复章节正文")
    return warnings
