from pathlib import Path

from paper_rag.parsers.xml_parser import XmlParser


def test_jats_xml_parser(tmp_path: Path):
    path = tmp_path / "paper.xml"
    path.write_text(
        """<?xml version="1.0"?>
        <article><front><article-meta><title-group><article-title>Trial</article-title></title-group>
        <abstract><p>Structured abstract.</p></abstract></article-meta></front>
        <body><sec><title>Methods</title><p>We measured sleep.</p></sec>
        <sec><title>Results</title><p>We found an association.</p></sec></body></article>""",
        encoding="utf-8",
    )
    parsed = XmlParser().parse(path)
    assert parsed.title == "Trial"
    assert parsed.abstract == "Structured abstract."
    assert [section.section_type for section in parsed.sections] == ["abstract", "methods", "results"]


def test_tei_parser_preserves_parent_section_type_for_subsections(tmp_path: Path):
    path = tmp_path / "paper.xml"
    path.write_text(
        """<?xml version="1.0"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt><title>Nested Paper</title></titleStmt>
              <publicationStmt><p>Published</p></publicationStmt>
              <sourceDesc><p>Source</p></sourceDesc>
            </fileDesc>
          </teiHeader>
          <text>
            <body>
              <div><head>Introduction</head><p>Background text.</p></div>
              <div>
                <head>Materials and methods</head>
                <div><head>Human sample</head><p>Human cohort details.</p></div>
                <div><head>Cell lines and reagents</head><p>Cell culture details.</p></div>
                <div><head>RNA sequencing</head><p>Sequencing protocol.</p></div>
                <div><head>Statistical analysis</head><p>Statistics protocol.</p></div>
              </div>
              <div>
                <head>Results</head>
                <div><head>High expression of TIM predicts survival</head><p>Survival result.</p></div>
                <div><head>TIM enhances tumor growth</head><p>Growth result.</p></div>
                <div><head>TIM promotes metastasis</head><p>Metastasis result.</p></div>
                <div><head>ACER2 is responsible for TIM signaling</head><p>Signaling result.</p></div>
              </div>
              <div><head>Discussion</head><p>Interpretation text.</p></div>
            </body>
          </text>
        </TEI>""",
        encoding="utf-8",
    )

    parsed = XmlParser().parse(path)

    by_title = {section.title: section for section in parsed.sections}
    assert by_title["Introduction"].section_type == "introduction"
    assert by_title["Discussion"].section_type == "discussion"
    assert by_title["Human sample"].section_type == "methods"
    assert by_title["Human sample"].parent_title == "Materials and methods"
    assert by_title["Statistical analysis"].section_type == "methods"
    assert by_title["Statistical analysis"].parent_title == "Materials and methods"
    assert by_title["High expression of TIM predicts survival"].section_type == "results"
    assert by_title["High expression of TIM predicts survival"].parent_title == "Results"
    assert by_title["ACER2 is responsible for TIM signaling"].section_type == "results"
    assert by_title["ACER2 is responsible for TIM signaling"].parent_title == "Results"
