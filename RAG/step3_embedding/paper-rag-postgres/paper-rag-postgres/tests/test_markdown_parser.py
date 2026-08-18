from pathlib import Path

from paper_rag.parsers.markdown_parser import MarkdownParser


def test_markdown_parser_uses_headings(tmp_path: Path):
    path = tmp_path / "paper.md"
    filler = "Scientific evidence is reported in this sentence. " * 20
    path.write_text(
        f"# Markdown Paper\n\n## Abstract\n{filler}\n\n"
        f"## Methods\n{filler}\n\n## Results\n{filler}",
        encoding="utf-8",
    )
    parsed = MarkdownParser().parse(path)
    assert parsed.title == "Markdown Paper"
    assert parsed.abstract.startswith("Scientific evidence")
    assert [section.section_type for section in parsed.sections] == [
        "abstract", "methods", "results"
    ]
