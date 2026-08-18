from __future__ import annotations

from lxml import etree

from paper_rag.domain import ParsedAsset, ParsedDocument, ParsedSection
from paper_rag.text_utils import normalize_section_type, normalize_whitespace


def _text(node: etree._Element | None) -> str:
    if node is None:
        return ""
    return normalize_whitespace(" ".join(node.itertext()))


def _section_type_for_title(title: str, inherited_section_type: str | None) -> str:
    section_type = normalize_section_type(title)
    if section_type == "other" and inherited_section_type:
        return inherited_section_type
    return section_type


def parse_tei_bytes(content: bytes, parser_name: str = "grobid") -> ParsedDocument:
    root = etree.fromstring(content, parser=etree.XMLParser(recover=True, huge_tree=True))
    ns = {"tei": "http://www.tei-c.org/ns/1.0"}

    title_nodes = root.xpath("//tei:teiHeader//tei:titleStmt/tei:title[1]", namespaces=ns)
    title = _text(title_nodes[0]) if title_nodes else ""

    abstract_nodes = root.xpath("//tei:profileDesc//tei:abstract[1]", namespaces=ns)
    abstract = _text(abstract_nodes[0]) if abstract_nodes else ""
    authors = [
        value
        for node in root.xpath("//tei:teiHeader//tei:sourceDesc//tei:author", namespaces=ns)
        if (value := _text(node))
    ]
    date_nodes = root.xpath(
        "//tei:teiHeader//tei:publicationStmt/tei:date[1] | "
        "//tei:teiHeader//tei:sourceDesc//tei:date[1]",
        namespaces=ns,
    )
    publication_date = ""
    if date_nodes:
        publication_date = date_nodes[0].get("when") or _text(date_nodes[0])

    sections: list[ParsedSection] = []
    order = 0
    if abstract:
        sections.append(ParsedSection("Abstract", "abstract", order, abstract))
        order += 1

    def visit_div(
        div: etree._Element,
        inherited_section_type: str | None = None,
        parent_title: str | None = None,
    ) -> None:
        nonlocal order
        head = div.find("{http://www.tei-c.org/ns/1.0}head")
        section_title = _text(head) or "Untitled section"
        section_type = _section_type_for_title(section_title, inherited_section_type)
        own_paragraphs = div.xpath("./tei:p | ./tei:list/tei:item", namespaces=ns)
        paragraphs = [_text(node) for node in own_paragraphs]
        body = normalize_whitespace("\n\n".join(p for p in paragraphs if p))
        if body:
            sections.append(
                ParsedSection(
                    title=section_title,
                    section_type=section_type,
                    order=order,
                    text=body,
                    parent_title=parent_title,
                )
            )
            order += 1
        for child_div in div.xpath("./tei:div", namespaces=ns):
            visit_div(child_div, section_type, section_title)

    for body_node in root.xpath("//tei:text/tei:body", namespaces=ns):
        for div in body_node.xpath("./tei:div", namespaces=ns):
            visit_div(div)

    assets: list[ParsedAsset] = []
    for figure in root.xpath("//tei:figure", namespaces=ns):
        label_nodes = figure.xpath("./tei:head | ./tei:label", namespaces=ns)
        caption_nodes = figure.xpath("./tei:figDesc", namespaces=ns)
        asset_type = "table" if figure.get("type", "").lower() == "table" else "figure"
        label = _text(label_nodes[0]) if label_nodes else asset_type.title()
        caption = _text(caption_nodes[0]) if caption_nodes else ""
        if caption:
            content_nodes = figure.xpath("./tei:table", namespaces=ns)
            content_text = _text(content_nodes[0]) if content_nodes else None
            assets.append(ParsedAsset(asset_type, label, caption, content=content_text))

    references = []
    for item in root.xpath("//tei:listBibl/tei:biblStruct | //tei:listBibl/tei:bibl", namespaces=ns):
        value = _text(item)
        if value:
            references.append(value)

    quality = "high" if len(sections) >= 4 and sum(len(s.text) for s in sections) >= 5000 else "medium"
    return ParsedDocument(
        title=title,
        abstract=abstract,
        sections=sections,
        assets=assets,
        references=references,
        parser_name=parser_name,
        quality=quality,
        metadata={"authors": authors, "publication_date": publication_date},
    )
