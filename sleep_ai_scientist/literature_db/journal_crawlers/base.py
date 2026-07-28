from __future__ import annotations

from abc import ABC, abstractmethod

from .metadata_parser import discover_html_links, parse_article_html, parse_feed, parse_sitemap


class JournalAdapter(ABC):
    name="base";version="1"
    @abstractmethod
    def discover(self,content:str,base_url:str)->list[str]:...
    def parse_article(self,content:str,url:str):return parse_article_html(content,url)


class GenericMetaTagsAdapter(JournalAdapter):
    name="generic_meta_tags"
    def discover(self,content,base_url):
        links=discover_html_links(content,base_url);return links["article"]+links["listing"]


class GenericJsonLdAdapter(GenericMetaTagsAdapter):name="generic_jsonld"
class RssAtomAdapter(JournalAdapter):
    name="rss_atom"
    def discover(self,content,base_url):return parse_feed(content)
class SitemapAdapter(JournalAdapter):
    name="sitemap"
    def discover(self,content,base_url):return parse_sitemap(content)
