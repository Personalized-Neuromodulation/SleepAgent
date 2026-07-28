from __future__ import annotations

import json
import re
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin
from xml.etree import ElementTree

from .models import CrawledPaperMetadata


class _HeadParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.meta={}; self.links=[]; self.scripts=[]; self._jsonld=False; self._buf=[]
    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if tag=="meta":
            key=(values.get("name") or values.get("property") or "").casefold()
            if key and values.get("content") is not None:self.meta.setdefault(key,[]).append(values["content"].strip())
        elif tag=="link" and values.get("href"):
            self.links.append(values)
        elif tag=="script" and values.get("type","").casefold()=="application/ld+json":self._jsonld=True;self._buf=[]
    def handle_data(self,data):
        if self._jsonld:self._buf.append(data)
    def handle_endtag(self,tag):
        if tag=="script" and self._jsonld:self.scripts.append("".join(self._buf));self._jsonld=False


def _first(meta,*keys):
    for key in keys:
        values=meta.get(key.casefold())
        if values:return values[0]
    return None


def _authors(value):
    values=value if isinstance(value,list) else [value] if value else []
    rows=[]
    for item in values:
        if isinstance(item,dict):
            name=item.get("name") or " ".join(filter(None,[item.get("givenName"),item.get("familyName")]))
        else:name=str(item)
        bits=name.strip().split(); rows.append({"given_name":" ".join(bits[:-1]) or None,"family_name":bits[-1] if bits else None,"raw":item})
    return rows


def _is_article_node(node):
    if not isinstance(node, dict):
        return False
    node_types = node.get("@type", [])
    if isinstance(node_types, str):
        node_types = [node_types]
    return bool(
        isinstance(node_types, list)
        and {"ScholarlyArticle", "Article", "MedicalScholarlyArticle"}.intersection(node_types)
    )


def parse_article_html(html: str, url: str) -> CrawledPaperMetadata | None:
    parser=_HeadParser();parser.feed(html)
    scholarly=None
    for raw in parser.scripts:
        try:data=json.loads(raw)
        except Exception:continue
        nodes=data.get("@graph",[]) if isinstance(data,dict) else data if isinstance(data,list) else []
        if isinstance(data,dict):nodes=[data,*nodes]
        scholarly=next((x for x in nodes if _is_article_node(x)),None)
        if scholarly:break
    meta=parser.meta; ld=scholarly or {}
    title=ld.get("headline") or ld.get("name") or _first(meta,"citation_title","dc.title","og:title")
    if not title:return None
    author_values=ld.get("author") or meta.get("citation_author",[])
    identifiers=ld.get("identifier")
    doi=_first(meta,"citation_doi","dc.identifier")
    if not doi and isinstance(identifiers,str) and "10." in identifiers:doi=identifiers
    journal=_first(meta,"citation_journal_title","prism.publicationname")
    part=ld.get("isPartOf")
    if not journal and isinstance(part,dict):journal=part.get("name")
    first=_first(meta,"citation_firstpage","prism.startingpage");last=_first(meta,"citation_lastpage","prism.endingpage")
    keywords=ld.get("keywords") or _first(meta,"citation_keywords","keywords") or []
    if isinstance(keywords,str):keywords=[x.strip() for x in keywords.replace(";",",").split(",") if x.strip()]
    return CrawledPaperMetadata(
        source_url=url,title=str(title).strip(),authors=_authors(author_values),
        abstract=ld.get("abstract") or _first(meta,"citation_abstract","dc.description","description"),
        journal=journal,publication_date=ld.get("datePublished") or _first(meta,"citation_publication_date","dc.date","prism.publicationdate"),
        doi=doi,volume=str(ld.get("volumeNumber") or _first(meta,"citation_volume","prism.volume") or "") or None,
        issue=str(ld.get("issueNumber") or _first(meta,"citation_issue","prism.number") or "") or None,
        pages=f"{first}-{last}" if first and last else first,
        article_type=(ld.get("@type")[0] if isinstance(ld.get("@type"),list) and ld.get("@type") else ld.get("@type")),
        language=ld.get("inLanguage"),
        keywords=keywords,raw_metadata={"json_ld":ld,"meta":meta},discovery_channel="web_crawl")


def discover_html_links(html: str, base_url: str) -> dict[str,list[str]]:
    parser=_HeadParser();parser.feed(html);result={"rss":[],"sitemap":[],"article":[],"listing":[]}
    for link in parser.links:
        href=urljoin(base_url,link["href"]);rel=" ".join(link.get("rel",[])) if isinstance(link.get("rel"),list) else link.get("rel","");typ=link.get("type","")
        if "rss" in typ or "atom" in typ:result["rss"].append(href)
    class AParser(HTMLParser):
        def __init__(self):
            super().__init__();self.href=None;self.text=[]
        def handle_starttag(self,tag,attrs):
            if tag!="a":return
            href=dict(attrs).get("href")
            if not href:return
            self.href=urljoin(base_url,href);self.text=[]
        def handle_data(self,data):
            if self.href:self.text.append(data)
        def handle_endtag(self,tag):
            if tag!="a" or not self.href:return
            absolute=self.href;low=absolute.casefold();label=" ".join(self.text).strip().casefold()
            if "sitemap" in low:result["sitemap"].append(absolute)
            elif any(x in low for x in ("/rss","/feed","atom.xml")):result["rss"].append(absolute)
            elif any(x in low or x in label for x in (
                "latest articles","latest research","current issue","online first",
                "early view","advance articles","all issues","archive","browse articles",
                "/toc","/issue/","/issues","/latest","/recent","/archive",
            )):result["listing"].append(absolute)
            elif any(x in low for x in (
                "/article/","/articles/","/doi/","/content/","/full/","/abstract/",
                "/science/article/",
            )) and not any(x in low for x in (
                "/article-types/","/article-collections/",
                "/services/aop-",
            )) and not re.search(r"\.(?:pdf|xml|ris|bib)(?:[?#]|$)",low):result["article"].append(absolute)
            elif re.search(r"/20\d{2}/\d+/e?\d+(?:[/?#]|$)", low):
                result["article"].append(absolute)
            self.href=None;self.text=[]
    p=AParser();p.feed(html)
    return {k:list(dict.fromkeys(v)) for k,v in result.items()}


def discover_search_forms(html: str, base_url: str) -> list[dict]:
    """Find public GET search forms and describe enough evidence to replay them."""

    class FormParser(HTMLParser):
        def __init__(self):
            super().__init__();self.current=None;self.forms=[]
        def handle_starttag(self,tag,attrs):
            values=dict(attrs)
            if tag=="form":
                self.current={"action":urljoin(base_url,values.get("action") or base_url),"method":(values.get("method") or "get").casefold(),"role":values.get("role"),"id":values.get("id"),"class":values.get("class"),"inputs":[]}
            elif self.current is not None and tag in {"input","textarea","select"}:
                self.current["inputs"].append({key:values.get(key) for key in ("name","type","value","placeholder","aria-label","id")})
        def handle_endtag(self,tag):
            if tag=="form" and self.current is not None:
                self.forms.append(self.current);self.current=None

    parser=FormParser();parser.feed(html);result=[]
    for form in parser.forms:
        visible=[x for x in form["inputs"] if (x.get("type") or "text").casefold() not in {"hidden","submit","button","reset","checkbox","radio"} and x.get("name")]
        candidates=[]
        for field in visible:
            evidence=" ".join(str(field.get(key) or "") for key in ("name","placeholder","aria-label","id")).casefold()
            score=sum(token in evidence for token in ("search","query","keyword","term","find","article"))
            if score:candidates.append((score,field))
        action_evidence=" ".join(str(form.get(key) or "") for key in ("action","role","id","class")).casefold()
        if not candidates and visible and ("search" in action_evidence or form.get("role")=="search"):
            candidates=[(1,visible[0])]
        if not candidates:continue
        _,query_field=max(candidates,key=lambda row:row[0])
        fixed={x["name"]:x.get("value") or "" for x in form["inputs"] if x.get("name") and (x.get("type") or "").casefold()=="hidden"}
        params={**fixed,query_field["name"]:"{query}"}
        separator="&" if "?" in form["action"] else "?"
        template=form["action"]+separator+urlencode(params).replace("%7Bquery%7D","{query}")
        result.append({**form,"query_field":query_field["name"],"fixed_params":fixed,"url_template":template,"supported":form["method"]=="get"})
    return result


def render_search_url(template: str, query: str) -> str:
    from urllib.parse import quote_plus
    return template.replace("{query}",quote_plus(query))


def parse_feed(xml: str) -> list[str]:
    root=ElementTree.fromstring(xml);urls=[]
    for record in root.iter():
        if record.tag.rsplit("}",1)[-1].casefold() not in {"item","entry"}:
            continue
        for item in record.iter():
            name=item.tag.rsplit("}",1)[-1].casefold()
            if name=="link":
                value=item.attrib.get("href") or (item.text or "").strip()
                if value and value.startswith("http"):urls.append(value)
                break
    return list(dict.fromkeys(urls))


def parse_jats_xml(xml: str, url: str) -> CrawledPaperMetadata | None:
    root=ElementTree.fromstring(xml)
    def nodes(name):
        return [node for node in root.iter() if node.tag.rsplit("}",1)[-1].casefold()==name.casefold()]
    def first(name):
        found=nodes(name)
        return " ".join("".join(found[0].itertext()).split()) if found else None
    title=first("article-title")
    if not title:return None
    doi=None
    for node in nodes("article-id"):
        if (node.attrib.get("pub-id-type") or "").casefold()=="doi":doi=(node.text or "").strip() or None;break
    authors=[]
    for contrib in nodes("contrib"):
        if (contrib.attrib.get("contrib-type") or "author").casefold()!="author":continue
        surname=next((" ".join("".join(x.itertext()).split()) for x in contrib.iter() if x.tag.rsplit("}",1)[-1].casefold()=="surname"),None)
        given=next((" ".join("".join(x.itertext()).split()) for x in contrib.iter() if x.tag.rsplit("}",1)[-1].casefold()=="given-names"),None)
        if surname or given:authors.append({"given_name":given,"family_name":surname,"raw":{"given":given,"surname":surname}})
    publication_date=None
    pub_dates=nodes("pub-date")
    if pub_dates:
        parts={}
        for child in pub_dates[0]:
            key=child.tag.rsplit("}",1)[-1].casefold()
            if key in {"year","month","day"}:parts[key]=(child.text or "").strip()
        if parts.get("year"):
            publication_date="-".join(filter(None,[parts["year"],parts.get("month","").zfill(2) or None,parts.get("day","").zfill(2) or None]))
    return CrawledPaperMetadata(
        source_url=url.removesuffix("/xml"),title=title,authors=authors,
        abstract=first("abstract"),journal=first("journal-title"),
        publication_date=publication_date,doi=doi,article_type=root.attrib.get("article-type") or "journal-article",
        raw_metadata={"jats_xml":True},discovery_channel="web_crawl",discovery_provider="publisher_jats",
    )


def parse_feed_metadata(xml: str) -> list[CrawledPaperMetadata]:
    """Parse RSS/Atom/RDF item metadata without requiring blocked article pages."""

    root = ElementTree.fromstring(xml)

    def local(node) -> str:
        return node.tag.rsplit("}", 1)[-1].casefold()

    def text(node, *names):
        wanted = {name.casefold() for name in names}
        for child in node.iter():
            if local(child) in wanted and (child.text or "").strip():
                return " ".join(unescape(child.text or "").split())
        return None

    channel_journal = None
    for node in root.iter():
        if local(node) in {"channel", "feed"}:
            channel_journal = text(node, "publicationName")
            break
    rows = []
    for node in root.iter():
        if local(node) not in {"item", "entry"}:
            continue
        title = text(node, "title")
        if not title:
            continue
        link = None
        for child in node.iter():
            if local(child) == "link":
                link = child.attrib.get("href") or (child.text or "").strip()
                if link:
                    break
        doi = text(node, "doi", "identifier", "guid")
        if doi:
            match = re.search(r"10\.\d{4,9}/\S+", doi)
            doi = match.group(0).rstrip(" .") if match else None
        if not link and doi:
            link = f"https://doi.org/{doi}"
        if not link:
            continue
        publication_date = text(node, "date", "published", "updated", "pubDate", "coverDate")
        if publication_date and "," in publication_date:
            try:
                publication_date = parsedate_to_datetime(publication_date).date().isoformat()
            except (TypeError, ValueError):
                pass
        creators = []
        for child in node.iter():
            if local(child) not in {"creator", "author"}:
                continue
            name = text(child, "name") if list(child) else " ".join((child.text or "").split())
            if not name:
                continue
            bits = name.split()
            creators.append(
                {
                    "given_name": " ".join(bits[:-1]) or None,
                    "family_name": bits[-1],
                    "raw": name,
                }
            )
        feed_section = text(node, "section", "type", "category")
        description = text(node, "description", "summary", "encoded")
        rows.append(
            CrawledPaperMetadata(
                source_url=link,
                title=title,
                authors=creators,
                abstract=description,
                journal=text(node, "publicationName") or channel_journal,
                publication_date=publication_date,
                doi=doi,
                volume=text(node, "volume"),
                issue=text(node, "number", "issue"),
                article_type="journal-article",
                raw_metadata={"publisher_feed": True, "feed_section": feed_section},
                discovery_channel="web_crawl",
                discovery_provider="publisher_feed",
            )
        )
    return rows


def parse_sitemap(xml: str) -> list[str]:
    root=ElementTree.fromstring(xml)
    return list(dict.fromkeys((node.text or "").strip() for node in root.iter() if node.tag.rsplit("}",1)[-1]=="loc" and (node.text or "").strip()))
