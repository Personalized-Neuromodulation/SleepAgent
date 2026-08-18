import json
from pathlib import Path

from paper_rag.parsers.json_parser import JsonParser


def test_json_parser_supports_structured_sections(tmp_path: Path):
    path = tmp_path / "paper.json"
    filler = "Scientific result and supporting evidence. " * 30
    path.write_text(
        json.dumps(
            {
                "title": "JSON Paper",
                "abstract": "A structured abstract. " + filler,
                "authors": ["Ann Smith"],
                "publication_date": "2025-03-01",
                "sections": [
                    {"title": "Methods", "text": filler},
                    {"title": "Results", "content": filler},
                ],
                "tables": [{"label": "Table 1", "caption": "Primary results", "text": filler}],
            }
        ),
        encoding="utf-8",
    )
    parsed = JsonParser().parse(path)
    assert parsed.title == "JSON Paper"
    assert parsed.metadata["authors"] == ["Ann Smith"]
    assert {section.section_type for section in parsed.sections} >= {"abstract", "methods", "results"}
    assert parsed.assets[0].asset_type == "table"
