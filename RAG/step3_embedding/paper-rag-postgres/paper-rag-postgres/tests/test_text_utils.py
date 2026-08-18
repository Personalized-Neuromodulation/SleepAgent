from pathlib import Path

import pytest

from paper_rag.text_utils import normalize_doi, normalize_section_type, sha256_file, validate_real_format


def test_normalize_doi():
    assert normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"
    assert normalize_doi("doi: 10.1234/Test") == "10.1234/test"


def test_normalize_section_type_common_scientific_headings():
    assert normalize_section_type("2. Materials and Methods") == "methods"
    assert normalize_section_type("Experimental Procedures") == "methods"
    assert normalize_section_type("Findings") == "results"
    assert normalize_section_type("Discussion and conclusions") == "discussion"


def test_validate_real_formats(tmp_path: Path):
    pdf = tmp_path / "paper.bin"
    pdf.write_bytes(b"%PDF-1.7\nexample")
    mime, warnings = validate_real_format(pdf)
    assert mime == "application/pdf"
    assert warnings

    xml = tmp_path / "paper.xml"
    xml.write_text("<?xml version='1.0'?><article><body/></article>", encoding="utf-8")
    assert validate_real_format(xml)[0] == "application/xml"
    assert len(sha256_file(xml)) == 64

    json_file = tmp_path / "paper.data"
    json_file.write_text('{"title":"Paper","full_text":"content"}', encoding="utf-8")
    assert validate_real_format(json_file)[0] == "application/json"

    markdown = tmp_path / "paper.md"
    markdown.write_text("# Paper\n\n## Methods\nContent", encoding="utf-8")
    assert validate_real_format(markdown)[0] == "text/markdown"


def test_reject_robot_page(tmp_path: Path):
    page = tmp_path / "paper.txt"
    page.write_text("<html><title>Robot verification</title></html>", encoding="utf-8")
    with pytest.raises(ValueError):
        validate_real_format(page)


def test_reject_plain_txt(tmp_path: Path):
    path = tmp_path / "paper.txt"
    path.write_text("plain text without markdown structure", encoding="utf-8")
    with pytest.raises(ValueError, match="不支持TXT"):
        validate_real_format(path)
