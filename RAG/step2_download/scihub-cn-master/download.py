#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch-download legally available open-access full text from DOI rows in a CSV. Prefer PDF globally and validate XML/JSON full text before reporting success.

Sources (configurable):
  unpaywall, pubmed, europe_pmc, openalex, semantic_scholar, pmc, crossref

Important:
- PubMed is an index, not usually a full-text host. This source resolves DOI -> PMID -> PMC.
- Europe PMC can return OA full-text XML when a PMCID is available.
- OpenAlex and Semantic Scholar are used to discover OA PDF URLs.
- No paywall, login, CAPTCHA, robots restriction, or institutional-access bypass is attempted.

Examples:
  python download_fulltext_multi_source.py papers.csv --email you@example.com
  python download_fulltext_multi_source.py papers.csv --sources europe_pmc,openalex,semantic_scholar,pubmed

Optional environment variables:
  NCBI_API_KEY       NCBI E-utilities API key
  S2_API_KEY         Semantic Scholar Graph API key
  OPENALEX_API_KEY   OpenAlex API key, if your deployment requires one
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import quote, urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOG = logging.getLogger("fulltext")

UNPAYWALL_API = "https://api.unpaywall.org/v2/{doi}"
CROSSREF_API = "https://api.crossref.org/works/{doi}"
OPENALEX_API = "https://api.openalex.org/works/https://doi.org/{doi}"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPE_PMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_ELINK = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
PMC_ID_CONVERTER = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
PMC_BIOC = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{pmcid}/unicode"

DEFAULT_SOURCES = [
    "publisher_pdf",
    "unpaywall",
    "openalex",
    "semantic_scholar",
    "crossref",
    "pubmed",
    "europe_pmc",
    "pmc",
]

NO_PROXY_VALUES = {"", "0", "none", "no", "false", "off", "direct"}
PROXY_SCHEMES = ("http://", "https://", "socks4://", "socks4a://", "socks5://", "socks5h://")


def normalize_proxy(proxy: Optional[str]) -> Optional[str]:
    value = str(proxy or "").strip()
    if value.lower() in NO_PROXY_VALUES:
        return None
    lower = value.lower()
    if lower.startswith("socks5://"):
        return "socks5h://" + value[len("socks5://"):]
    if lower.startswith(PROXY_SCHEMES):
        return value
    return "http://" + value


@dataclass
class Result:
    status: str
    source: str = ""
    fmt: str = ""
    url: str = ""
    file: str = ""
    markdown_file: str = ""
    http_status: str = ""
    identifier: str = ""
    error: str = ""


def normalize_doi(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    return value.strip().lower()


def safe_name(value: str, limit: int = 100) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or ""))
    value = re.sub(r"\s+", " ", value).strip(" ._")
    return value[:limit].rstrip(" ._") or "untitled"


def make_stem(doi: str, title: str) -> str:
    return safe_name(title or doi, 160)


def detect_encoding(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            path.read_text(encoding=encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def unique_urls(values: Iterable[Tuple[str, Optional[str]]]) -> List[Tuple[str, Optional[str]]]:
    output: List[Tuple[str, Optional[str]]] = []
    seen: Set[str] = set()
    for url, expected in values:
        url = str(url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        output.append((url, expected))
    return output


class Downloader:
    def __init__(
        self,
        out_dir: Path,
        email: str,
        timeout: int = 45,
        delay: Tuple[float, float] = (0.8, 1.8),
        overwrite: bool = False,
        sources: Optional[Sequence[str]] = None,
        flat_output: bool = False,
        proxy: Optional[str] = None,
    ) -> None:
        self.out_dir = out_dir
        self.email = email
        self.timeout = timeout
        self.delay = delay
        self.overwrite = overwrite
        self.flat_output = flat_output
        self.proxy = normalize_proxy(proxy)
        self.sources = list(sources or DEFAULT_SOURCES)
        self.ncbi_api_key = os.getenv("NCBI_API_KEY", "").strip()
        self.s2_api_key = os.getenv("S2_API_KEY", "s2k-UBcTYeR1Wu6oLdOPEooueysXchKs0pu26A1Zv2vd").strip()
        self.openalex_api_key = os.getenv("OPENALEX_API_KEY", "RbfrULWTgikcvf6HTt8K2P").strip()
        self.session = self._make_session()
        if flat_output:
            self.dirs = {
                "pdf": out_dir,
                "xml": out_dir,
                "json": out_dir,
                "html": out_dir,
                "md": out_dir,
                "markdown": out_dir,
            }
        else:
            self.dirs = {
                "pdf": out_dir / "pdf",
                "xml": out_dir / "xml",
                "json": out_dir / "json",
                "html": out_dir / "html",
                "md": out_dir / "converted" / "markdown",
                "markdown": out_dir / "converted" / "markdown",
            }
        for directory in self.dirs.values():
            directory.mkdir(parents=True, exist_ok=True)

    def _make_session(self) -> requests.Session:
        retry = Retry(
            # Keep retries bounded. Large connect/read retry counts can turn one
            # SSL/proxy failure into many minutes of repeated requests.
            total=2,
            connect=2,
            read=1,
            status=2,
            backoff_factor=1.0,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "User-Agent": f"OAFulltextDownloader/2.0 (mailto:{self.email})",
            "Accept": "application/pdf,application/xml,application/json,text/html;q=0.8,*/*;q=0.5",
        })
        session.trust_env = True
        if self.proxy:
            session.proxies.update({
                "http": self.proxy,
                "https": self.proxy,
            })
        return session

    def pause(self) -> None:
        time.sleep(random.uniform(*self.delay))

    def _request_with_429_retry(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        allow_redirects: bool = True,
        stream: bool = False,
        **kwargs,
    ):
        """Request with an explicit 429 retry schedule: 3s -> 6s -> 7s.

        429 is intentionally NOT handled by urllib3 Retry, otherwise the
        adapter retry and this retry loop would multiply each other.
        """
        wait_schedule = (3, 6, 7)
        response = None

        for attempt in range(len(wait_schedule) + 1):
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                headers=headers,
                timeout=timeout or self.timeout,
                allow_redirects=allow_redirects,
                stream=stream,
                **kwargs,
            )

            if response.status_code != 429:
                return response

            if attempt >= len(wait_schedule):
                LOG.warning(
                    "  HTTP 429: 已完成3次等待重试，当前来源放弃: %s",
                    url,
                )
                return response

            wait_seconds = wait_schedule[attempt]
            LOG.warning(
                "  HTTP 429: 等待 %s 秒后重试 (%s/3): %s",
                wait_seconds,
                attempt + 1,
                url,
            )
            try:
                response.close()
            except Exception:
                pass
            time.sleep(wait_seconds)

        return response

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.pause()
        response = self._request_with_429_retry(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def is_block_page(data: bytes, ctype: str) -> bool:
        if "html" not in ctype and not data.lstrip().startswith(b"<"):
            return False
        text = data[:300_000].decode("utf-8", "ignore").lower()
        return any(marker in text for marker in (
            "checking your browser", "just a moment", "captcha", "access denied",
            "institutional login", "purchase this article", "subscribe to read",
            "sign in to access", "verify you are human",
        ))


    @staticmethod
    def _html_soup(html: str):
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(html or "", "html.parser")
        except ImportError:
            return None

    @staticmethod
    def _is_fulltext_asset_url(url: str, fmt: str) -> bool:
        """Reject obvious site/config/static assets masquerading as XML/JSON."""
        low = str(url or "").strip().lower()
        if not low:
            return False

        # Nature and many publisher pages expose browser/site configuration
        # XML in <meta> / <link> tags. These are NOT article full text.
        blocked_markers = (
            "browserconfig.xml",
            "manifest.xml",
            "manifest.json",
            "site.webmanifest",
            "favicon",
            "sitemap",
            "robots.txt",
            "/oscar-static/",
            "/static/",
            "/assets/",
            "/webpack/",
            "/frontend/",
        )
        if any(marker in low for marker in blocked_markers):
            return False

        # Reject obvious supplementary/supporting material unless the caller
        # has explicitly discovered it through a known full-text metadata field.
        if any(marker in low for marker in (
            "supplementary",
            "supplemental",
            "suppinfo",
            "supporting-information",
        )):
            return False

        path = low.split("?", 1)[0].split("#", 1)[0]
        if fmt == "pdf":
            return path.endswith(".pdf")
        if fmt == "xml":
            return path.endswith(".xml")
        if fmt == "json":
            return path.endswith(".json")
        if fmt == "md":
            return path.endswith(".md")
        return False

    @classmethod
    def extract_html_fulltext_links(cls, html: str, base_url: str) -> List[Tuple[str, str]]:
        """Extract only high-confidence article full-text links.

        Important: arbitrary <meta content="...xml"> values are NOT treated as
        full text. This prevents publisher assets such as
        /oscar-static/browserconfig.xml from entering the download loop.
        """
        soup = cls._html_soup(html)
        if soup is None:
            return []

        found: List[Tuple[str, str]] = []
        seen = set()

        def add(raw_url: str, fmt: str, trusted: bool = False) -> None:
            raw_url = str(raw_url or "").strip()
            if not raw_url:
                return
            absolute = urljoin(base_url or "", raw_url)
            if not trusted and not cls._is_fulltext_asset_url(absolute, fmt):
                return
            # Even trusted metadata must never accept known static/config assets.
            if not cls._is_fulltext_asset_url(absolute, fmt):
                return
            key = (absolute, fmt)
            if key in seen:
                return
            seen.add(key)
            found.append(key)

        # Only explicit scholarly full-text metadata names are trusted.
        meta_format_names = {
            "citation_pdf_url": "pdf",
            "eprints.document_url": "pdf",
            "dc.identifier.pdf": "pdf",
            "citation_xml_url": "xml",
            "eprints.document_url.xml": "xml",
            "dc.identifier.xml": "xml",
        }

        for meta in soup.find_all("meta"):
            name = str(
                meta.get("name")
                or meta.get("property")
                or ""
            ).strip().lower()
            content = str(meta.get("content") or "").strip()
            if not content:
                continue

            fmt = meta_format_names.get(name)
            if fmt:
                add(content, fmt, trusted=True)

        # Direct anchors only. Site <link> resources are intentionally ignored,
        # because they frequently point to browserconfig/manifest/static XML.
        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "").strip()
            text_value = " ".join(a.stripped_strings).lower()
            low = href.lower().split("?", 1)[0].split("#", 1)[0]

            if low.endswith(".pdf"):
                # Skip obvious supplements.
                if "supplement" not in text_value and "supplement" not in low:
                    add(href, "pdf")
            elif low.endswith(".xml"):
                # XML anchors need article/full-text evidence in URL or label.
                if any(token in (low + " " + text_value) for token in (
                    "fulltext", "full-text", "article", "jats", "download"
                )):
                    add(href, "xml")
            elif low.endswith(".json"):
                if any(token in (low + " " + text_value) for token in (
                    "fulltext", "full-text", "article", "bioc", "download"
                )):
                    add(href, "json")
            elif low.endswith(".md"):
                if "download" in text_value or "fulltext" in low:
                    add(href, "md")
            elif "download" in text_value and "bitstream" in href.lower():
                # Repository bitstream links are commonly PDFs; content type
                # is still verified by fetch_file().
                absolute = urljoin(base_url or "", href)
                key = (absolute, "pdf")
                if key not in seen:
                    seen.add(key)
                    found.append(key)

        rank = {"pdf": 0, "xml": 1, "json": 2, "md": 3}
        return sorted(found, key=lambda x: rank.get(x[1], 99))

    @staticmethod
    def _is_editorial_digest(text: str, title: str = "") -> bool:
        low = (text or "").lower()
        normalized_title = re.sub(r"^[#\s]+", "", title or "").strip().lower()
        if normalized_title.startswith((
            "daily briefing:",
            "nature briefing:",
            "audio long read:",
        )):
            return True

        digest_markers = (
            "hello nature readers",
            "briefing in your inbox",
            "quote of the day",
            "thanks for reading",
            "senior editor, nature briefing",
        )
        return sum(1 for marker in digest_markers if marker in low) >= 2

    @classmethod
    def classify_html_page(cls, html: str) -> str:
        """
        Return one of:
            landing  - metadata/repository/download page, not article body
            fulltext - likely full article HTML
            unknown  - insufficient evidence

        Long HTML is NOT automatically treated as full text.
        """
        soup = cls._html_soup(html)
        if soup is None:
            return "unknown"

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = " ".join(soup.stripped_strings)
        low = text.lower()
        page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if cls._is_editorial_digest(text, page_title):
            return "landing"

        landing_score = 0
        fulltext_score = 0

        meta_names = {
            str(m.get("name") or m.get("property") or "").strip().lower()
            for m in soup.find_all("meta")
        }

        if "citation_pdf_url" in meta_names:
            landing_score += 6
        if "citation_abstract_html_url" in meta_names:
            landing_score += 2

        generator = soup.find("meta", attrs={"name": re.compile(r"^generator$", re.I)})
        generator_value = str(generator.get("content") or "").lower() if generator else ""
        if any(x in generator_value for x in ("dspace", "eprints")):
            landing_score += 5

        for term in (
            "view item",
            "search repository",
            "view item statistics",
            "upload full text",
            "publication year",
            "publication type",
            "this item appears in the following collection",
        ):
            if term in low:
                landing_score += 1

        access_terms = (
            "access options",
            "access nature and",
            "subscribe to this journal",
            "rent or buy this article",
            "purchase this article",
            "get nature+",
            "prices may be subject to local taxes",
        )
        access_score = sum(1 for term in access_terms if term in low)
        landing_score += access_score
        if "related articles" in low and "access options" in low:
            landing_score += 1

        section_terms = (
            "abstract",
            "introduction",
            "materials and methods",
            "methods",
            "results",
            "discussion",
            "conclusion",
            "references",
        )
        section_count = sum(1 for term in section_terms if term in low)
        fulltext_score += section_count

        article = soup.find("article")
        article_text = ""
        if article is not None:
            fulltext_score += 4
            article_text = " ".join(article.stripped_strings)

        paragraph_count = len([
            p for p in soup.find_all("p")
            if len(" ".join(p.stripped_strings)) >= 80
        ])
        if paragraph_count >= 8:
            fulltext_score += 3
        elif paragraph_count >= 4:
            fulltext_score += 1

        strong_fulltext = (
            section_count >= 4
            and paragraph_count >= 8
            and len(article_text or text) >= 5000
        )

        # Repositories exposing downloadable full text are landing pages.
        if cls.extract_html_fulltext_links(html, ""):
            landing_score += 3

        if access_score >= 2 and not strong_fulltext:
            return "landing"
        if landing_score >= 6 and landing_score >= fulltext_score and not strong_fulltext:
            return "landing"
        if fulltext_score >= 4 and section_count >= 2 and len(text) >= 3000:
            return "fulltext"
        return "unknown"

    def resolve_html_landing_page(
        self,
        html: str,
        base_url: str,
        stem: str,
        visited: Optional[Set[str]] = None,
        landing_depth: int = 0,
    ) -> Optional[Result]:
        """Follow a bounded set of direct full-text links from a landing page."""
        visited = visited if visited is not None else set()

        # One landing-page hop is enough for repository/publisher resolution.
        # More recursion is usually a redirect loop, not a new full-text path.
        if landing_depth >= 2:
            LOG.info(
                "  HTML landing page: 达到最大解析深度，停止继续递归: %s",
                base_url,
            )
            return None

        for link, expected_fmt in self.extract_html_fulltext_links(
            html,
            base_url,
        ):
            canonical = str(link or "").strip()
            if not canonical or canonical in visited:
                LOG.debug("  跳过已访问全文链接: %s", canonical)
                continue

            LOG.info(
                "  HTML landing page -> 尝试直接全文链接 %s: %s",
                expected_fmt.upper(),
                canonical,
            )

            result = self.fetch_file(
                canonical,
                stem,
                expected=expected_fmt,
                _visited=visited,
                _landing_depth=landing_depth + 1,
            )

            if (
                result.status == "downloaded"
                and self.validate_fulltext_file(result)
            ):
                result.source = "html_landing"
                return result

            if result.file:
                try:
                    Path(result.file).unlink(missing_ok=True)
                except OSError:
                    pass

        return None

    def fetch_file(
        self,
        url: str,
        stem: str,
        expected: Optional[str] = None,
        _visited: Optional[Set[str]] = None,
        _landing_depth: int = 0,
    ) -> Result:
        """Fetch one candidate without recursive landing-page loops."""
        self.pause()

        visited = _visited if _visited is not None else set()
        request_url = str(url or "").strip()
        if not request_url:
            return Result("failed", url=url, error="空URL")

        if request_url in visited:
            return Result(
                "failed",
                url=request_url,
                error="检测到重复URL/landing-page循环，已跳过",
            )

        visited.add(request_url)

        try:
            response = self._request_with_429_retry(
                "GET",
                request_url,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True,
            )
            status = str(response.status_code)
            response.raise_for_status()

            final_url = str(response.url or request_url)
            # Record the redirect destination as visited, but do not reject this
            # first response merely because it differs from the requested URL.
            visited.add(final_url)

            chunks: List[bytes] = []
            total = 0
            for chunk in response.iter_content(128 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > 100 * 1024 * 1024:
                    return Result(
                        "failed",
                        url=final_url,
                        http_status=status,
                        error="文件超过100 MB",
                    )
                chunks.append(chunk)

            data = b"".join(chunks)
            ctype = (
                response.headers.get("Content-Type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )

            if not data:
                return Result(
                    "failed",
                    url=final_url,
                    http_status=status,
                    error="空响应",
                )

            if self.is_block_page(data, ctype):
                return Result(
                    "failed",
                    url=final_url,
                    http_status=status,
                    error="返回登录、付费或验证页面",
                )

            if (
                data.startswith(b"%PDF-")
                or ctype in {"application/pdf", "application/x-pdf"}
            ):
                fmt = "pdf"

            elif ctype == "application/json":
                fmt = "json"

            elif "xml" in ctype or data.lstrip().startswith(b"<?xml"):
                fmt = "xml"

            elif ctype in {"text/markdown", "text/x-markdown"} or (
                expected == "md" and ctype == "text/plain"
            ):
                fmt = "md"

            elif "html" in ctype:
                # CRITICAL:
                # If a supposedly-direct PDF/XML/JSON/MD URL redirects back to
                # HTML, do NOT resolve that HTML again. That behavior caused the
                # Nature ".pdf -> article HTML -> .pdf -> ..." infinite loop.
                if expected in {"pdf", "xml", "json", "md"}:
                    return Result(
                        "failed",
                        url=final_url,
                        http_status=status,
                        error=(
                            f"期望直接{expected.upper()}，但返回HTML/重定向到landing页；"
                            "为防止递归循环已停止该候选"
                        ),
                    )

                html = data.decode("utf-8", "ignore")
                page_type = self.classify_html_page(html)

                if page_type == "landing":
                    followed = self.resolve_html_landing_page(
                        html=html,
                        base_url=final_url,
                        stem=stem,
                        visited=visited,
                        landing_depth=_landing_depth,
                    )
                    if followed is not None:
                        return followed
                    return Result(
                        "failed",
                        url=final_url,
                        http_status=status,
                        error=(
                            "HTML是landing/metadata页，且未找到可下载的"
                            "有效PDF/XML/JSON/MD全文"
                        ),
                    )

                if page_type != "fulltext":
                    return Result(
                        "failed",
                        url=final_url,
                        http_status=status,
                        error=(
                            "HTML未确认是文章全文页"
                            f"（classification={page_type}）"
                        ),
                    )

                fmt = "html"

            else:
                return Result(
                    "failed",
                    url=final_url,
                    http_status=status,
                    error=f"未知内容类型: {ctype}",
                )

            # Strict format verification. Never trust filename extension alone.
            if expected == "pdf" and fmt != "pdf":
                return Result(
                    "failed",
                    url=final_url,
                    http_status=status,
                    error=f"期望PDF，实际为 {ctype or fmt}",
                )
            if expected == "xml" and fmt != "xml":
                return Result(
                    "failed",
                    url=final_url,
                    http_status=status,
                    error=f"期望XML，实际为 {ctype or fmt}",
                )
            if expected == "json" and fmt != "json":
                return Result(
                    "failed",
                    url=final_url,
                    http_status=status,
                    error=f"期望JSON，实际为 {ctype or fmt}",
                )
            if expected == "md" and fmt != "md":
                return Result(
                    "failed",
                    url=final_url,
                    http_status=status,
                    error=f"期望Markdown，实际为 {ctype or fmt}",
                )

            target = self.dirs[fmt] / f"{stem}.{fmt}"
            if not target.exists() or self.overwrite:
                target.write_bytes(data)

            return Result(
                "downloaded",
                fmt=fmt,
                url=final_url,
                file=str(target),
                http_status=status,
            )

        except requests.RequestException as exc:
            status = str(
                getattr(
                    getattr(exc, "response", None),
                    "status_code",
                    "",
                )
                or ""
            )
            return Result(
                "failed",
                url=request_url,
                http_status=status,
                error=str(exc),
            )
        except OSError as exc:
            return Result(
                "failed",
                url=request_url,
                error=f"写文件失败: {exc}",
            )

    @classmethod
    def validate_fulltext_file(cls, result: Result) -> bool:
        """确认已下载文件确实包含正文，而不是题录、错误响应或空壳。"""
        if result.status != "downloaded" or not result.file:
            return False

        path = Path(result.file)
        if not path.exists() or path.stat().st_size <= 0:
            return False

        if result.fmt == "pdf":
            try:
                return path.read_bytes()[:5] == b"%PDF-"
            except OSError:
                return False

        if result.fmt == "xml":
            try:
                root = ET.parse(path).getroot()
                body = root.find(".//body")
                if body is None:
                    return False
                body_text = " ".join("".join(body.itertext()).split())
                return len(body_text) >= 500
            except (ET.ParseError, OSError):
                return False

        if result.fmt == "json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                text_parts: List[str] = []

                def collect(value: Any) -> None:
                    if isinstance(value, dict):
                        for key, item in value.items():
                            if key.lower() in {"text", "paragraph", "sentence"} and isinstance(item, str):
                                text_parts.append(item)
                            else:
                                collect(item)
                    elif isinstance(value, list):
                        for item in value:
                            collect(item)

                collect(data)
                return len(" ".join(text_parts)) >= 500
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                return False

        if result.fmt == "html":
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if cls.classify_html_page(content) != "fulltext":
                    return False
                soup = cls._html_soup(content)
                if soup is not None:
                    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                        tag.decompose()
                    text = " ".join(soup.stripped_strings)
                else:
                    text = re.sub(r"<[^>]+>", " ", content)
                return len(text) >= 1000
            except OSError:
                return False

        if result.fmt == "md":
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                low = content.lower()
                headings = re.findall(r"^#{1,6}\s+(.+?)\s*$", content, flags=re.MULTILINE)
                document_title = headings[0] if headings else ""
                if cls._is_editorial_digest(content, document_title):
                    return False
                access_terms = (
                    "access options",
                    "access nature and",
                    "subscribe to this journal",
                    "rent or buy this article",
                    "purchase this article",
                    "get nature+",
                    "prices may be subject to local taxes",
                )
                section_terms = (
                    "abstract",
                    "introduction",
                    "materials and methods",
                    "methods",
                    "results",
                    "discussion",
                    "conclusion",
                    "references",
                )
                access_score = sum(1 for term in access_terms if term in low)
                section_count = sum(
                    1
                    for heading in headings
                    if any(
                        re.sub(r"[^a-z ]", "", heading.lower()).strip().startswith(term)
                        for term in section_terms
                    )
                )
                paragraph_count = len([
                    line for line in content.splitlines()
                    if len(line.strip()) >= 80
                ])
                strong_fulltext = (
                    section_count >= 4
                    and paragraph_count >= 8
                    and len(content.strip()) >= 5000
                )
                if access_score >= 2 and not strong_fulltext:
                    return False
                return section_count >= 2 and paragraph_count >= 8 and len(content.strip()) >= 1000
            except OSError:
                return False

        return False

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip()

    @classmethod
    def _xml_node_text(cls, node: Optional[ET.Element]) -> str:
        if node is None:
            return ""
        return cls._clean_text("".join(node.itertext()))

    @classmethod
    def _jats_section_to_markdown(cls, section: ET.Element, level: int = 2) -> List[str]:
        lines: List[str] = []
        title = cls._xml_node_text(section.find("./title"))
        if title:
            lines.extend([f"{'#' * min(max(level, 2), 6)} {title}", ""])

        for paragraph in section.findall("./p"):
            value = cls._xml_node_text(paragraph)
            if value:
                lines.extend([value, ""])

        for figure in section.findall("./fig"):
            label = cls._xml_node_text(figure.find("./label")) or "Figure"
            caption = cls._xml_node_text(figure.find("./caption"))
            if caption:
                lines.extend([f"> **{label}:** {caption}", ""])

        for table in section.findall("./table-wrap"):
            label = cls._xml_node_text(table.find("./label")) or "Table"
            caption = cls._xml_node_text(table.find("./caption"))
            if caption:
                lines.extend([f"> **{label}:** {caption}", ""])

        for child in section.findall("./sec"):
            lines.extend(cls._jats_section_to_markdown(child, level + 1))
        return lines

    @classmethod
    def jats_xml_to_markdown(cls, xml_path: Path) -> str:
        root = ET.parse(xml_path).getroot()
        lines: List[str] = []

        title = cls._xml_node_text(root.find(".//article-title"))
        if title:
            lines.extend([f"# {title}", ""])

        author_names: List[str] = []
        for contrib in root.findall(".//contrib[@contrib-type='author']"):
            given = cls._xml_node_text(contrib.find(".//given-names"))
            surname = cls._xml_node_text(contrib.find(".//surname"))
            name = cls._clean_text(f"{given} {surname}")
            if name:
                author_names.append(name)
        if author_names:
            lines.extend([f"**Authors:** {'; '.join(author_names)}", ""])

        doi = ""
        for article_id in root.findall(".//article-id"):
            if article_id.attrib.get("pub-id-type", "").lower() == "doi":
                doi = cls._xml_node_text(article_id)
                break
        if doi:
            lines.extend([f"**DOI:** {doi}", ""])

        abstract = cls._xml_node_text(root.find(".//abstract"))
        if abstract:
            lines.extend(["## Abstract", "", abstract, ""])

        body = root.find(".//body")
        if body is None:
            raise ValueError("JATS XML不存在<body>正文节点")

        for paragraph in body.findall("./p"):
            value = cls._xml_node_text(paragraph)
            if value:
                lines.extend([value, ""])
        for section in body.findall("./sec"):
            lines.extend(cls._jats_section_to_markdown(section))

        references: List[str] = []
        for index, ref in enumerate(root.findall(".//ref-list/ref"), 1):
            label = cls._xml_node_text(ref.find("./label")) or str(index)
            citation = ref.find("./element-citation")
            if citation is None:
                citation = ref.find("./mixed-citation")
            if citation is None:
                citation = ref
            value = cls._xml_node_text(citation)
            if value:
                references.append(f"{label}. {value}")
        if references:
            lines.extend(["## References", ""])
            for value in references:
                lines.extend([value, ""])
        return "\n".join(lines).strip() + "\n"

    @classmethod
    def bioc_json_to_markdown(cls, json_path: Path, fallback_title: str = "") -> str:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        documents = data if isinstance(data, list) else [data]
        lines: List[str] = []
        title_written = False

        for document in documents:
            if not isinstance(document, dict):
                continue
            passages = document.get("passages") or []
            for passage in passages:
                if not isinstance(passage, dict):
                    continue
                infons = passage.get("infons") or {}
                section = cls._clean_text(str(
                    infons.get("section_type") or infons.get("type") or infons.get("section") or ""
                ))
                text_value = cls._clean_text(str(passage.get("text") or ""))
                if not text_value:
                    continue
                section_lower = section.lower()
                if not title_written and section_lower in {"title", "front"}:
                    lines.extend([f"# {text_value}", ""])
                    title_written = True
                    continue
                if section_lower in {"abstract"}:
                    lines.extend(["## Abstract", "", text_value, ""])
                elif section_lower and section_lower not in {"paragraph", "body"}:
                    lines.extend([f"## {section}", "", text_value, ""])
                else:
                    lines.extend([text_value, ""])

                for annotation in passage.get("annotations") or []:
                    _ = annotation  # BioC annotations are intentionally omitted from readable text.

        if not title_written and fallback_title:
            lines.insert(0, "")
            lines.insert(0, f"# {fallback_title}")
        markdown = "\n".join(lines).strip()
        if len(re.sub(r"[#*`>\s]", "", markdown)) < 500:
            raise ValueError("BioC JSON未提取到足够正文")
        return markdown + "\n"

    @classmethod
    def html_to_markdown(cls, html_path: Path, fallback_title: str = "") -> str:
        raw = html_path.read_text(encoding="utf-8", errors="ignore")
        page_type = cls.classify_html_page(raw)
        if page_type != "fulltext":
            raise ValueError(
                f"HTML不是可确认的文章全文页，禁止转换为正文Markdown: {page_type}"
            )
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            article = soup.find("article") or soup.find("main") or soup.body or soup
            title = ""
            if soup.title:
                title = cls._clean_text(soup.title.get_text(" ", strip=True))
            lines: List[str] = []
            if title or fallback_title:
                lines.extend([f"# {title or fallback_title}", ""])
            for node in article.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
                value = cls._clean_text(node.get_text(" ", strip=True))
                if not value:
                    continue
                if node.name.startswith("h"):
                    level = min(max(int(node.name[1]), 1), 6)
                    lines.extend([f"{'#' * level} {value}", ""])
                elif node.name == "li":
                    lines.append(f"- {value}")
                else:
                    lines.extend([value, ""])
            markdown = "\n".join(lines).strip()
        except ImportError:
            body = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
            body = re.sub(r"(?i)</?(h[1-6]|p|div|section|article|li|br)[^>]*>", "\n", body)
            body = re.sub(r"<[^>]+>", " ", body)
            markdown = cls._clean_text(body)
            if fallback_title:
                markdown = f"# {fallback_title}\n\n{markdown}"
        if len(re.sub(r"[#*`>\s]", "", markdown)) < 500:
            raise ValueError("HTML未提取到足够正文")
        return markdown + "\n"

    def convert_downloaded_fulltext(self, result: Result, doi: str, title: str) -> Result:
        """下载成功后立即把XML/JSON/HTML转换成Markdown。"""
        if result.status != "downloaded" or not result.file:
            return result
        if result.fmt in {"pdf", "md"}:
            return result

        source_path = Path(result.file)
        try:
            if result.fmt == "xml":
                markdown = self.jats_xml_to_markdown(source_path)
            elif result.fmt == "json":
                markdown = self.bioc_json_to_markdown(source_path, title)
            elif result.fmt == "html":
                markdown = self.html_to_markdown(source_path, title)
            else:
                return result

            md_path = self.dirs["markdown"] / f"{source_path.stem}.md"
            if self.overwrite or not md_path.exists():
                md_path.write_text(markdown, encoding="utf-8")
            result.markdown_file = str(md_path)
            if result.fmt == "html":
                source_path.unlink(missing_ok=True)
                result.fmt = "md"
                result.file = str(md_path)
            LOG.info("  已转换Markdown: %s", md_path)
        except Exception as exc:
            conversion_error = f"全文转换失败: {exc}"
            result.error = f"{result.error}；{conversion_error}" if result.error else conversion_error
            LOG.warning("  %s", conversion_error)
        return result

    def try_urls(self, source: str, identifier: str, stem: str,
                 urls: Iterable[Tuple[str, Optional[str]]]) -> Optional[Result]:
        for url, expected in unique_urls(urls):
            result = self.fetch_file(url, stem, expected)
            if result.status == "downloaded":
                result.source = source
                result.identifier = identifier
                return result
        return None

    # ---------- Europe PMC ----------
    def europe_pmc(self, doi: str, stem: str) -> Optional[Result]:
        data = self.get_json(EUROPE_PMC_SEARCH, {
            "query": f'DOI:"{doi}"',
            "format": "json",
            "resultType": "core",
            "pageSize": 5,
            "email": self.email,
        })
        records = ((data.get("resultList") or {}).get("result") or [])
        for record in records:
            pmcid = str(record.get("pmcid") or "").strip()
            if not pmcid:
                continue
            url = EUROPE_PMC_FULLTEXT.format(pmcid=quote(pmcid, safe=""))
            result = self.fetch_file(url, stem, "xml")
            if result.status == "downloaded":
                result.source = "Europe PMC"
                result.identifier = pmcid
                return result
        return None

    # ---------- PubMed -> PMC ----------
    def pubmed(self, doi: str, stem: str) -> Optional[Result]:
        params: Dict[str, Any] = {
            "db": "pubmed", "term": f'"{doi}"[AID]', "retmode": "json",
            "tool": "oa_fulltext_downloader", "email": self.email,
        }
        if self.ncbi_api_key:
            params["api_key"] = self.ncbi_api_key
        search = self.get_json(NCBI_ESEARCH, params)
        pmids = ((search.get("esearchresult") or {}).get("idlist") or [])
        for pmid in pmids:
            link_params: Dict[str, Any] = {
                "dbfrom": "pubmed", "db": "pmc", "id": pmid,
                "linkname": "pubmed_pmc", "retmode": "json",
                "tool": "oa_fulltext_downloader", "email": self.email,
            }
            if self.ncbi_api_key:
                link_params["api_key"] = self.ncbi_api_key
            linked = self.get_json(NCBI_ELINK, link_params)
            pmc_numeric: List[str] = []
            for linkset in linked.get("linksets") or []:
                for dbset in linkset.get("linksetdbs") or []:
                    pmc_numeric.extend(str(x) for x in dbset.get("links") or [])
            for numeric in pmc_numeric:
                pmcid = f"PMC{numeric}"
                # Prefer Europe PMC JATS XML, then NCBI BioC JSON.
                xml_url = EUROPE_PMC_FULLTEXT.format(pmcid=pmcid)
                result = self.fetch_file(xml_url, stem, "xml")
                if result.status == "downloaded":
                    result.source = "PubMed → PMC"
                    result.identifier = f"PMID:{pmid};{pmcid}"
                    return result
                bioc_url = PMC_BIOC.format(pmcid=pmcid)
                result = self.fetch_file(bioc_url, stem, "json")
                if result.status == "downloaded":
                    result.source = "PubMed → PMC BioC"
                    result.identifier = f"PMID:{pmid};{pmcid}"
                    return result
        return None

    # ---------- OpenAlex ----------
    def openalex(self, doi: str, stem: str) -> Optional[Result]:
        params: Dict[str, Any] = {"mailto": self.email}
        if self.openalex_api_key:
            params["api_key"] = self.openalex_api_key
        data = self.get_json(OPENALEX_API.format(doi=quote(doi, safe="")), params)
        locations: List[Dict[str, Any]] = []
        for key in ("best_oa_location", "primary_location"):
            location = data.get(key)
            if isinstance(location, dict):
                locations.append(location)
        for location in data.get("locations") or []:
            if isinstance(location, dict):
                locations.append(location)

        urls: List[Tuple[str, Optional[str]]] = []
        for location in locations:
            pdf_url = str(location.get("pdf_url") or "").strip()
            landing = str(location.get("landing_page_url") or "").strip()
            if pdf_url:
                urls.append((pdf_url, "pdf"))
            # Landing page is tried only if it directly serves a confirmed full-text document.
            if landing:
                urls.append((landing, None))
        return self.try_urls("OpenAlex", str(data.get("id") or ""), stem, urls)

    # ---------- Semantic Scholar ----------
    def semantic_scholar(self, doi: str, stem: str) -> Optional[Result]:
        headers = {"x-api-key": self.s2_api_key} if self.s2_api_key else None
        data = self.get_json(
            SEMANTIC_SCHOLAR_API.format(doi=quote(doi, safe="")),
            params={"fields": "paperId,title,url,openAccessPdf,externalIds"},
            headers=headers,
        )
        oa = data.get("openAccessPdf") or {}
        urls: List[Tuple[str, Optional[str]]] = []
        if isinstance(oa, dict) and oa.get("url"):
            urls.append((str(oa["url"]), "pdf"))
        return self.try_urls("Semantic Scholar", str(data.get("paperId") or ""), stem, urls)

    # ---------- Unpaywall ----------
    def unpaywall(self, doi: str, stem: str) -> Optional[Result]:
        data = self.get_json(UNPAYWALL_API.format(doi=quote(doi, safe="")), {"email": self.email})
        locations: List[Dict[str, Any]] = []
        if isinstance(data.get("best_oa_location"), dict):
            locations.append(data["best_oa_location"])
        for location in data.get("oa_locations") or []:
            if isinstance(location, dict):
                locations.append(location)
        urls: List[Tuple[str, Optional[str]]] = []
        for location in locations:
            if location.get("url_for_pdf"):
                urls.append((str(location["url_for_pdf"]), "pdf"))
            if location.get("url_for_landing_page"):
                urls.append((str(location["url_for_landing_page"]), None))
        return self.try_urls("Unpaywall", doi, stem, urls)

    # ---------- DOI -> PMC ID Converter -> PMC BioC ----------
    def pmc(self, doi: str, stem: str) -> Optional[Result]:
        data = self.get_json(
            PMC_ID_CONVERTER,
            {
                "ids": doi,
                "format": "json",
                "tool": "oa_fulltext_downloader",
                "email": self.email,
            },
        )
        records = data.get("records") or []
        for record in records:
            pmcid = str(record.get("pmcid") or "").strip()
            if not pmcid:
                continue
            url = PMC_BIOC.format(pmcid=quote(pmcid, safe=""))
            result = self.fetch_file(url, stem, "json")
            if result.status == "downloaded":
                result.source = "PMC BioC"
                result.identifier = pmcid
                return result
        return None

    # ---------- Crossref ----------
    def crossref(self, doi: str, stem: str) -> Optional[Result]:
        data = self.get_json(CROSSREF_API.format(doi=quote(doi, safe="")), {"mailto": self.email})
        urls: List[Tuple[str, Optional[str]]] = []
        for item in ((data.get("message") or {}).get("link") or []):
            url = str(item.get("URL") or "").strip()
            declared = str(item.get("content-type") or "").lower()
            expected = "pdf" if "pdf" in declared else "xml" if "xml" in declared else None
            urls.append((url, expected))
        return self.try_urls("Crossref link", doi, stem, urls)

    # ---------- Publisher direct PDF ----------
    def publisher_pdf(self, doi: str, stem: str) -> Optional[Result]:
        article_id = doi.split("/", 1)[1] if "/" in doi else ""
        urls: List[Tuple[str, Optional[str]]] = []
        if doi.startswith("10.1038/") and article_id:
            article_url = f"https://www.nature.com/articles/{quote(article_id, safe='')}"
            try:
                from bs4 import BeautifulSoup
                response = self._request_with_429_retry(
                    "GET",
                    article_url,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                if response.status_code == 200 and "html" in response.headers.get("Content-Type", "").lower():
                    soup = BeautifulSoup(response.text, "html.parser")
                    for tag in soup.find_all(["a", "link"], href=True):
                        href = str(tag.get("href") or "").strip()
                        text = tag.get_text(" ", strip=True).lower()
                        path = href.split("?", 1)[0].lower()
                        if not path.endswith(".pdf"):
                            continue
                        if "supplement" in text or "supplement" in href.lower():
                            continue
                        if "download pdf" in text or path.endswith(f"/{article_id.lower()}_reference.pdf"):
                            urls.insert(0, (urljoin(response.url, href), "pdf"))
            except Exception as exc:
                LOG.info("  Publisher PDF page parsing failed: %s", exc)
        return self.try_urls("Publisher PDF", doi, stem, urls)

    def one(self, doi: str, title: str) -> Result:
        """
        Download one article.

        Final preference:
            PDF > XML > JSON > MD > HTML

        PDF wins immediately.
        For non-PDF full text, keep the highest-quality fallback found across
        all configured sources instead of simply keeping the first fallback.
        """
        doi = normalize_doi(doi)
        if not doi:
            return Result("invalid_doi", error="DOI为空或无效")

        stem = make_stem(doi, title)
        methods: Dict[str, Callable[[str, str], Optional[Result]]] = {
            "publisher_pdf": self.publisher_pdf,
            "unpaywall": self.unpaywall,
            "pubmed": self.pubmed,
            "europe_pmc": self.europe_pmc,
            "openalex": self.openalex,
            "semantic_scholar": self.semantic_scholar,
            "pmc": self.pmc,
            "crossref": self.crossref,
        }

        # Lower number = higher preference.
        fallback_priority = {
            "xml": 0,
            "json": 1,
            "md": 2,
            "html": 3,
        }

        errors: List[str] = []
        fallback_result: Optional[Result] = None

        for source in self.sources:
            method = methods[source]
            try:
                LOG.info("  尝试来源: %s", source)
                result = method(doi, stem)
                if not result:
                    continue

                if not self.validate_fulltext_file(result):
                    errors.append(f"{source}: 下载文件未通过全文校验")
                    LOG.warning(
                        "  来源 %s 返回的文件未检测到有效正文，继续尝试其他来源: %s",
                        source,
                        result.file or result.url,
                    )
                    try:
                        if result.file:
                            Path(result.file).unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue

                # PDF is always the final winner.
                if result.fmt == "pdf":
                    LOG.info("  已获得PDF全文，停止继续搜索: %s", result.file)
                    return result

                # Ignore unexpected non-PDF formats.
                if result.fmt not in fallback_priority:
                    LOG.info("  忽略未纳入优先级的格式: %s", result.fmt)
                    continue

                if fallback_result is None:
                    fallback_result = result
                    LOG.info(
                        "  当前最佳非PDF全文=%s，继续搜索PDF或更高优先级格式: %s",
                        result.fmt.upper(),
                        result.file,
                    )
                    continue

                current_rank = fallback_priority.get(fallback_result.fmt, 999)
                new_rank = fallback_priority.get(result.fmt, 999)

                if new_rank < current_rank:
                    LOG.info(
                        "  非PDF全文升级: %s -> %s",
                        fallback_result.fmt.upper(),
                        result.fmt.upper(),
                    )
                    fallback_result = result
                else:
                    LOG.info(
                        "  已有更高或相同优先级非PDF全文=%s，当前%s仅作为冗余文件",
                        fallback_result.fmt.upper(),
                        result.fmt.upper(),
                    )

            except requests.HTTPError as exc:
                response = exc.response
                status = response.status_code if response is not None else ""
                if status not in (404, 410):
                    errors.append(f"{source}: HTTP {status} {exc}")
            except Exception as exc:
                errors.append(f"{source}: {exc}")

        if fallback_result is not None:
            return fallback_result

        return Result(
            "no_open_fulltext",
            error="；".join(errors) or "所有来源均未找到可公开下载全文",
        )


def read_csv(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    with path.open("r", encoding=detect_encoding(path), newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_status(rows: Sequence[Dict[str, str]], fields: Sequence[str],
                 results: Sequence[Result], path: Path) -> None:
    added = [
        "fulltext_status", "fulltext_source", "fulltext_format", "fulltext_identifier",
        "fulltext_url", "fulltext_file", "fulltext_markdown_file",
        "fulltext_http_status", "fulltext_error",
    ]
    out_fields = [field for field in fields if field != "fulltext_text_file"]
    out_fields += [field for field in added if field not in out_fields]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        for row, result in zip(rows, results):
            item = dict(row)
            item.update({
                "fulltext_status": result.status,
                "fulltext_source": result.source,
                "fulltext_format": result.fmt,
                "fulltext_identifier": result.identifier,
                "fulltext_url": result.url,
                "fulltext_file": result.file,
                "fulltext_markdown_file": result.markdown_file,
                "fulltext_http_status": result.http_status,
                "fulltext_error": result.error,
            })
            writer.writerow(item)


def parse_sources(value: str) -> List[str]:
    allowed = set(DEFAULT_SOURCES)
    result: List[str] = []
    for item in value.split(","):
        source = item.strip().lower()
        if not source:
            continue
        if source not in allowed:
            raise argparse.ArgumentTypeError(
                f"未知来源 {source!r}；可用值: {','.join(DEFAULT_SOURCES)}"
            )
        if source not in result:
            result.append(source)
    if not result:
        raise argparse.ArgumentTypeError("至少指定一个来源")
    return result


DEFAULT_CSV_FILE = Path(
    r"D:\crawler2025\crawler_light\exports\sleep\cell\Cell\sleep_related_2020-01-01_2027-07-28.csv"
)
DEFAULT_OUTPUT_DIR = Path(
    r"D:\crawler2025\crawler_light\exports\sleep\cell\Cell"
    r"\fulltext"
)
# 建议在系统环境变量 UNPAYWALL_EMAIL 中设置真实邮箱。
# 未设置环境变量时，请将下面的占位邮箱改成你自己的邮箱。
DEFAULT_EMAIL = os.getenv("UNPAYWALL_EMAIL", "m19993615519@163.com")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据CSV中的DOI下载合法开放获取全文，并自动将XML/JSON/HTML转换为Markdown")

    # nargs="?" 使脚本在不传任何命令行参数时直接使用默认CSV。
    parser.add_argument(
        "csv_file",
        nargs="?",
        type=Path,
        default=DEFAULT_CSV_FILE,
        help=f"输入CSV；默认: {DEFAULT_CSV_FILE}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"全文输出目录；默认: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--email",
        default=DEFAULT_EMAIL,
        help="API联系邮箱；默认读取UNPAYWALL_EMAIL，否则使用脚本中的DEFAULT_EMAIL",
    )
    parser.add_argument(
        "--sources",
        type=parse_sources,
        default=list(DEFAULT_SOURCES),
        help="逗号分隔；默认: " + ",".join(DEFAULT_SOURCES),
    )
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--proxy", default="none", help="Proxy URL, host:port, or none/direct/off to disable proxies.")
    parser.add_argument("--min-delay", type=float, default=0.8)
    parser.add_argument("--max-delay", type=float, default=1.8)
    parser.add_argument("--overwrite", action="store_true", default=False)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.csv_file.exists():
        print(f"输入文件不存在: {args.csv_file}", file=os.sys.stderr)
        return 2
    if not args.email or "@" not in args.email:
        print("请通过 --email 或 UNPAYWALL_EMAIL 提供联系邮箱", file=os.sys.stderr)
        return 2
    if args.min_delay < 0 or args.max_delay < args.min_delay:
        print("延迟参数无效", file=os.sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(args.output_dir / "download.log", encoding="utf-8"),
        ],
    )

    rows, fields = read_csv(args.csv_file)
    lower_fields = {field.lower(): field for field in fields}
    doi_field = lower_fields.get("doi")
    title_field = lower_fields.get("title")
    if not doi_field:
        LOG.error("CSV必须包含doi列")
        return 2

    downloader = Downloader(
        out_dir=args.output_dir,
        email=args.email,
        timeout=args.timeout,
        delay=(args.min_delay, args.max_delay),
        overwrite=args.overwrite,
        sources=args.sources,
        proxy=args.proxy,
    )

    results: List[Result] = []
    cache: Dict[str, Result] = {}
    for index, row in enumerate(rows, 1):
        doi = normalize_doi(row.get(doi_field, ""))
        title = row.get(title_field, "") if title_field else ""
        LOG.info("[%d/%d] %s | %s", index, len(rows), doi or "无DOI", title)
        if doi and doi in cache:
            previous = cache[doi]
            result = Result(**previous.__dict__)
            result.status = "duplicate_doi_" + previous.status
        else:
            result = downloader.one(doi, title)
            result = downloader.convert_downloaded_fulltext(result, doi, title)
            if doi:
                cache[doi] = result
        results.append(result)
        LOG.info(
            "  结果=%s 来源=%s 原始文件=%s Markdown=%s",
            result.status, result.source or "-", result.file or "-",
            result.markdown_file or "-",
        )
        write_status(rows[:len(results)], fields, results, args.output_dir / "download_results.partial.csv")

    final_path = args.output_dir / "download_results.csv"
    write_status(rows, fields, results, final_path)
    summary: Dict[str, int] = {}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    LOG.info("完成: %s", json.dumps(summary, ensure_ascii=False))
    LOG.info("结果表: %s", final_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
