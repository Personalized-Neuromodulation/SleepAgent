from __future__ import annotations

from pathlib import Path

from lxml import etree

from paper_rag.domain import ParsedAsset, ParsedDocument, ParsedSection
from paper_rag.parsers.base import DocumentParser
from paper_rag.parsers.tei import parse_tei_bytes
from paper_rag.text_utils import normalize_section_type, normalize_whitespace


def _node_text(node: etree._Element | None) -> str:
    return normalize_whitespace(" ".join(node.itertext())) if node is not None else ""


def _section_type_for_title(title: str, inherited_section_type: str | None) -> str:
    section_type = normalize_section_type(title)
    if section_type == "other" and inherited_section_type:
        return inherited_section_type
    return section_type


class XmlParser(DocumentParser):
    name = "xml-jats-tei"
    version = "1"

    def parse(self, path: Path) -> ParsedDocument:
        content = path.read_bytes()
        root = etree.fromstring(content, parser=etree.XMLParser(recover=True, huge_tree=True))
        if etree.QName(root).namespace == "http://www.tei-c.org/ns/1.0" or etree.QName(root).localname == "TEI":
            document = parse_tei_bytes(content, parser_name=self.name)
            document.parser_version = self.version
            return document

        title_nodes = root.xpath("//*[local-name()='article-title'][1]")
        title = _node_text(title_nodes[0]) if title_nodes else ""
        abstract_nodes = root.xpath("//*[local-name()='abstract'][1]")
        abstract = _node_text(abstract_nodes[0]) if abstract_nodes else ""
        authors: list[str] = []
        for contributor in root.xpath(
            "//*[local-name()='article-meta']/*[local-name()='contrib-group']/*[local-name()='contrib']"
        ):
            surname = contributor.xpath(".//*[local-name()='surname'][1]")
            given = contributor.xpath(".//*[local-name()='given-names'][1]")
            name = " ".join(
                value for value in (
                    _node_text(given[0]) if given else "",
                    _node_text(surname[0]) if surname else "",
                ) if value
            )
            if name:
                authors.append(name)
        date_nodes = root.xpath("//*[local-name()='article-meta']/*[local-name()='pub-date'][1]")
        publication_date = ""
        if date_nodes:
            year_nodes = date_nodes[0].xpath("./*[local-name()='year'][1]")
            month_nodes = date_nodes[0].xpath("./*[local-name()='month'][1]")
            day_nodes = date_nodes[0].xpath("./*[local-name()='day'][1]")
            parts = [
                _node_text(nodes[0]) if nodes else ""
                for nodes in (year_nodes, month_nodes, day_nodes)
            ]
            publication_date = "-".join(part for part in parts if part)

        sections: list[ParsedSection] = []
        order = 0
        if abstract:
            sections.append(ParsedSection("Abstract", "abstract", order, abstract))
            order += 1

        def visit_section(
            section: etree._Element,
            inherited_section_type: str | None = None,
            parent_title: str | None = None,
        ) -> None:
            nonlocal order
            section_titles = section.xpath("./*[local-name()='title'][1]")
            section_title = _node_text(section_titles[0]) if section_titles else "Untitled section"
            section_type = _section_type_for_title(section_title, inherited_section_type)
            paragraphs = section.xpath("./*[local-name()='p'] | ./*[local-name()='list']/*[local-name()='list-item']")
            body = normalize_whitespace("\n\n".join(_node_text(p) for p in paragraphs))
            if body:
                sections.append(
                    ParsedSection(
                        section_title,
                        section_type,
                        order,
                        body,
                        parent_title=parent_title,
                    )
                )
                order += 1
            for child_section in section.xpath("./*[local-name()='sec']"):
                visit_section(child_section, section_type, section_title)

        for body_node in root.xpath("//*[local-name()='body']"):
            for section in body_node.xpath("./*[local-name()='sec']"):
                visit_section(section)

        assets: list[ParsedAsset] = []
        for figure in root.xpath("//*[local-name()='fig']"):
            label_nodes = figure.xpath("./*[local-name()='label'][1]")
            caption_nodes = figure.xpath("./*[local-name()='caption'][1]")
            caption = _node_text(caption_nodes[0]) if caption_nodes else ""
            if caption:
                assets.append(
                    ParsedAsset(
                        "figure",
                        _node_text(label_nodes[0]) if label_nodes else "Figure",
                        caption,
                    )
                )

        for table in root.xpath("//*[local-name()='table-wrap']"):
            label_nodes = table.xpath("./*[local-name()='label'][1]")
            caption_nodes = table.xpath("./*[local-name()='caption'][1]")
            content_nodes = table.xpath(".//*[local-name()='table'][1]")
            caption = _node_text(caption_nodes[0]) if caption_nodes else ""
            content_text = _node_text(content_nodes[0]) if content_nodes else ""
            if caption or content_text:
                assets.append(
                    ParsedAsset(
                        "table",
                        _node_text(label_nodes[0]) if label_nodes else "Table",
                        caption,
                        content=content_text,
                    )
                )

        references = [
            value
            for node in root.xpath("//*[local-name()='ref-list']//*[local-name()='ref']")
            if (value := _node_text(node))
        ]
        quality = "high" if len(sections) >= 4 and sum(len(s.text) for s in sections) >= 5000 else "medium"
        return ParsedDocument(
            title=title,
            abstract=abstract,
            sections=sections,
            assets=assets,
            references=references,
            parser_name=self.name,
            parser_version=self.version,
            quality=quality,
            metadata={"authors": authors, "publication_date": publication_date},
        )
