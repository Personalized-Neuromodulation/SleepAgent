from paper_rag.domain import ParsedSection
from paper_rag.parsers.section_repair import repair_flat_section_hierarchy


def test_flat_other_sections_inherit_current_major_section_type():
    sections = [
        ParsedSection("Methods", "methods", 0, "Study setup."),
        ParsedSection("Sleep staging approaches", "other", 1, "Scoring protocol."),
        ParsedSection("Comparison of labelling methods", "other", 2, "Naming convention."),
        ParsedSection("Sleep metrics", "other", 3, "Metric definitions."),
        ParsedSection("Results", "results", 4, "Primary findings."),
    ]

    repaired = repair_flat_section_hierarchy(sections)

    by_title = {section.title: section for section in repaired}
    assert by_title["Sleep staging approaches"].section_type == "methods"
    assert by_title["Sleep staging approaches"].parent_title == "Methods"
    assert by_title["Comparison of labelling methods"].section_type == "methods"
    assert by_title["Comparison of labelling methods"].parent_title == "Methods"
    assert by_title["Sleep metrics"].section_type == "methods"
    assert by_title["Sleep metrics"].parent_title == "Methods"
    assert by_title["Results"].section_type == "results"
    assert by_title["Results"].parent_title is None


def test_short_label_sections_merge_into_previous_repaired_section():
    sections = [
        ParsedSection("Methods", "methods", 0, "Study setup."),
        ParsedSection("Comparison of labelling methods", "other", 1, "Naming convention:"),
        ParsedSection("S1", "other", 2, "Manual scoring by technician 1"),
        ParsedSection("S2", "other", 3, "Manual scoring by technician 2"),
        ParsedSection("Results", "results", 4, "Primary findings."),
    ]

    repaired = repair_flat_section_hierarchy(sections)

    assert [section.title for section in repaired] == [
        "Methods",
        "Comparison of labelling methods",
        "Results",
    ]
    comparison = repaired[1]
    assert comparison.section_type == "methods"
    assert comparison.parent_title == "Methods"
    assert "S1: Manual scoring by technician 1" in comparison.text
    assert "S2: Manual scoring by technician 2" in comparison.text
    assert [section.order for section in repaired] == [0, 1, 2]


def test_short_label_sections_stay_separate_without_definition_context():
    sections = [
        ParsedSection("Results", "results", 0, "Primary findings."),
        ParsedSection("N1", "other", 1, "Longer result narrative for this sleep stage."),
    ]

    repaired = repair_flat_section_hierarchy(sections)

    assert [section.title for section in repaired] == ["Results", "N1"]
    assert repaired[1].section_type == "results"
    assert repaired[1].parent_title == "Results"
