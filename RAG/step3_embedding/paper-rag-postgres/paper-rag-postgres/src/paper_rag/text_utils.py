from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path


SECTION_ALIASES = {
    "abstract": "abstract",
    "introduction": "introduction",
    "background": "introduction",
    "overview": "introduction",
    "materials and methods": "methods",
    "materials & methods": "methods",
    "material and methods": "methods",
    "material and method": "methods",
    "materials and method": "methods",
    "methods": "methods",
    "methodology": "methods",
    "experimental procedures": "methods",
    "experimental procedure": "methods",
    "experimental methods": "methods",
    "experimental method": "methods",
    "study design": "methods",
    "results": "results",
    "result": "results",
    "findings": "results",
    "finding": "results",
    "observations": "results",
    "observation": "results",
    "discussion": "discussion",
    "discussion and conclusion": "discussion",
    "discussion and conclusions": "discussion",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "data availability": "data_availability",
    "references": "references",
    "bibliography": "references",
}


def normalize_doi(value: str | None) -> str:
    doi = (value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
    return doi.strip()


def normalize_whitespace(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_section_type(title: str) -> str:
    key = re.sub(r"^\d+(?:\.\d+)*\s*", "", normalize_whitespace(title).lower()).strip(" :.-")
    if key in SECTION_ALIASES:
        return SECTION_ALIASES[key]
    for alias, section_type in SECTION_ALIASES.items():
        if key.startswith(alias):
            return section_type
    return "other"


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_whitespace(text).encode("utf-8")).hexdigest()


def validate_real_format(path: Path) -> tuple[str, list[str]]:
    suffix = path.suffix.lower().lstrip(".")
    head = path.read_bytes()[:4096]
    stripped = head.removeprefix(b"\xef\xbb\xbf").lstrip()
    warnings: list[str] = []

    if head.startswith(b"%PDF-"):
        if suffix != "pdf":
            warnings.append(f"扩展名.{suffix}与实际PDF格式不一致")
        return "application/pdf", warnings

    decoded_original = head.decode("utf-8", errors="replace")
    decoded = decoded_original.lower()
    # if stripped.startswith((b"<?xml", b"<article", b"<tei", b"<TEI")) and not (
    #     "<html" in decoded or "<!doctype html" in decoded
    # ):
    #     if suffix != "xml":
    #         warnings.append(f"扩展名.{suffix}与实际XML格式不一致")
    #     return "application/xml", warnings

    # if "<html" in decoded or "<!doctype html" in decoded:
    #     raise ValueError("文件实际是HTML页面，不是论文全文")
    if "<html" in decoded or "<!doctype html" in decoded:
        raise ValueError("文件实际是HTML页面，不是论文全文")

    if stripped.startswith(b"<"):
        if suffix != "xml":
            warnings.append(f"扩展名.{suffix}与实际XML格式不一致")
        return "application/xml", warnings
    
    if "verify you are human" in decoded or "robot verification" in decoded:
        raise ValueError("文件实际是机器人验证页面")
    if stripped.startswith((b"{", b"[")):
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"JSON格式无效: {exc}") from exc
        if suffix != "json":
            warnings.append(f"扩展名.{suffix}与实际JSON格式不一致")
        return "application/json", warnings

    if suffix == "txt":
        raise ValueError("不支持TXT全文；请提供PDF、XML、JSON或Markdown")

    markdown_markers = bool(
        re.search(r"(?m)^#{1,6}\s+\S", decoded_original)
        or re.search(r"(?m)^\s*[-*+]\s+\S", decoded_original)
    )
    if suffix in {"md", "markdown"} or markdown_markers:
        if suffix not in {"md", "markdown"}:
            warnings.append(f"扩展名.{suffix}与实际Markdown格式不一致")
        if "\ufffd" in decoded_original:
            warnings.append("文件头包含UTF-8替换字符")
        return "text/markdown", warnings

    raise ValueError(f"不支持或无法识别的文件格式: {suffix}")
