# -*- coding: utf-8 -*-
import os
import sys
import json
import logging
import time
import random
import re
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs
from dateutil import parser as dateparser
from bs4 import BeautifulSoup
from parser.text_cleanup import clean_metadata_text
from parser.doi_abstract import DoiAbstractFetcher
from tools.topic_utils import TopicConfig, article_matches_topic, build_search_keywords, dedupe_candidate_urls, is_challenge_page, summarize_counts, should_stop_keyword_paging

# 设置logger
logger = logging.getLogger(__name__)

_PLAYWRIGHT_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="crawler-playwright")
_PLAYWRIGHT_STATE = {
    "playwright": None,
    "browser": None,
    "page": None,
}
_PLAYWRIGHT_STATE_LOCK = threading.Lock()
_DETAIL_BROWSER_LOCK = threading.Lock()


# pandas导入（可选）
try:
    import pandas as pd
except ImportError:
    pd = None
    logger.warning("pandas未安装，某些功能可能不可用")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseParser:
    """基础解析器类"""
    
    def __init__(self, journal_type, paper_agent=None, use_browser=False):
        self.journal_type = journal_type
        self.paper_agent = paper_agent
        config = getattr(paper_agent, 'config', {}) if paper_agent else {}
        self.crawl_mode = str(config.get('CRAWL_MODE', 'archive_scan')).lower()
        self.use_browser = use_browser
        self.session = requests.Session()

        # Shared abstract repair client for ALL journal platforms.
        # It uses metadata APIs only and does not inherit the publisher-page
        # retry policy from self.session.
        self.abstract_fetcher = DoiAbstractFetcher(timeout=8)

        # Abstract repair is network-bound and may run in worker threads.
        # Each worker gets its own publisher Session and DOI fetcher.
        self.thread_safe_abstract_repair = True
        self._abstract_repair_local = threading.local()

        self.page = None
        self.browser = None
        self.playwright = None
        
        # 通用用户代理
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0'
        ]
        
        # 设置请求头（参考cell目录的成功配置）
        self.session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            # 增强反爬虫措施（参考cell目录成功配置）
            'Referer': 'https://www.cell.com/',
            'Origin': 'https://www.cell.com'
        })
        
        # 配置超时和重试
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=8,  # 进一步增加重试次数
            backoff_factor=5,  # 更长的退避时间
            status_forcelist=[403, 429, 500, 502, 503, 504],
            respect_retry_after_header=True
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        self.search_session = requests.Session()
        self.search_session.headers.update(self.session.headers)
        no_retry_adapter = HTTPAdapter(max_retries=0)
        self.search_session.mount('http://', no_retry_adapter)
        self.search_session.mount('https://', no_retry_adapter)

        # Publisher/article-page abstract repair session.
        #
        # IMPORTANT:
        # - zero HTTP retries
        # - no Playwright fallback in the abstract-repair path
        # - 403/429/challenge pages immediately fall back to doi_abstract.py
        self.publisher_session = requests.Session()
        self.publisher_session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
        })
        publisher_no_retry_adapter = HTTPAdapter(max_retries=0)
        self.publisher_session.mount('http://', publisher_no_retry_adapter)
        self.publisher_session.mount('https://', publisher_no_retry_adapter)

        try:
            self.publisher_abstract_timeout = max(
                1,
                int(config.get('PUBLISHER_ABSTRACT_TIMEOUT_SECONDS', 12))
            )
        except Exception:
            self.publisher_abstract_timeout = 12

        try:
            self.publisher_max_html_bytes = max(
                256 * 1024,
                int(config.get('PUBLISHER_MAX_HTML_BYTES', 3 * 1024 * 1024))
            )
        except Exception:
            self.publisher_max_html_bytes = 3 * 1024 * 1024


    def filter_topic_candidates(self, articles):
        if not self.paper_agent:
            return articles
        topic = TopicConfig(
            name=getattr(self.paper_agent, 'topic_name', 'topic'),
            keywords=list(getattr(self.paper_agent, 'topic_keywords', []) or [])
        )
        if not topic.keywords:
            return articles
        matched = [article for article in articles if article_matches_topic(article, topic)]
        logger.info(
            f"{self.journal_type}: topic keyword prefilter kept {len(matched)}/{len(articles)} "
            f"articles for topic {topic.name}"
        )
        return matched

    def _is_date_in_range(self, article_date, start_date, end_date):
        try:
            if isinstance(article_date, datetime):
                article_date = article_date.date()
            if isinstance(start_date, datetime):
                start_date = start_date.date()
            if isinstance(end_date, datetime):
                end_date = end_date.date()
            return start_date <= article_date <= end_date
        except Exception as e:
            logger.debug(f"日期范围检查失败: {e}")
            return False

    def should_use_topic_search(self):
        config = getattr(self.paper_agent, 'config', {}) if self.paper_agent else {}
        return str(config.get('CRAWL_MODE', '')).lower() == 'topic_search'

    def _progress(self, iterable, total=None, desc=''):
        try:
            from tqdm import tqdm
            return tqdm(iterable, total=total, desc=desc, unit='item', dynamic_ncols=True, leave=False)
        except Exception:
            return iterable

    def get_topic_search_keywords(self):
        topic = TopicConfig(
            name=getattr(self.paper_agent, 'topic_name', 'topic'),
            keywords=list(getattr(self.paper_agent, 'topic_keywords', []) or [])
        )
        return build_search_keywords(topic)

    def get_topic_search_max_pages(self):
        config = getattr(self.paper_agent, 'config', {}) if self.paper_agent else {}
        try:
            return max(1, int(config.get('TOPIC_SEARCH_MAX_PAGES_PER_KEYWORD', 3)))
        except Exception:
            return 3
    def ensure_browser_for_fallback(self):
        if self.page:
            return True
        logger.info(f"{self.journal_type}: 按需启动Playwright用于fallback")
        self._init_playwright()
        return self.page is not None



    def get_search_page_with_browser(self, search_url):
        try:
            return self.fetch_html_with_playwright(
                search_url,
                wait_selector=None,
                max_wait=0,
                settle_seconds=1,
            )
        except Exception as e:
            logger.warning(f"Playwright fetch failed {search_url}: {e}")
            return None

    def get_search_html_with_fallback(self, search_url, timeout=15):
        try:
            logger.info(f"{self.journal_type}: search requests尝试: {search_url}")
            response = self.search_session.get(search_url, timeout=timeout)
            html = response.text if response is not None else ""
            if response is not None and response.status_code == 200 and not is_challenge_page(html):
                return html
            status = getattr(response, "status_code", "unknown")
            logger.warning(f"{self.journal_type}: search HTTP {status}/challenge，切换Playwright fallback")
        except Exception as e:
            logger.warning(f"{self.journal_type}: search requests失败，切换Playwright fallback: {e}")

        return self.get_search_page_with_browser(search_url)

    def build_topic_search_url(self, journal_name, base_url, keyword, page=1):
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            return None
        query = quote_plus(keyword)
        site = parsed.netloc
        start = (page - 1) * 10
        return f"https://www.google.com/search?q=site:{site}+{query}&start={start}"

    def extract_candidate_urls_from_search_page(self, html, base_url):
        def normalize_host(host):
            host = (host or '').lower()
            return host[4:] if host.startswith('www.') else host

        parsed_base = urlparse(base_url)
        allowed_host = normalize_host(parsed_base.netloc)
        soup = BeautifulSoup(html, 'html.parser')
        urls = []
        for a in soup.find_all('a', href=True):
            href = urljoin(base_url, a['href'])
            parsed = urlparse(href)
            host = normalize_host(parsed.netloc)
            if allowed_host and not host.endswith(allowed_host):
                continue
            if host.endswith('journals.plos.org') and parsed.path.rstrip('/').endswith('/article') and not parsed.query:
                continue
            article_like_path = (
                '/articles/' in parsed.path or
                '/doi/' in parsed.path or
                parsed.path.endswith('/article') or
                '/article/' in parsed.path or
                '/abstract/' in parsed.path or
                '/fulltext/' in parsed.path
            )
            if article_like_path:
                urls.append(href)
        return urls

    def fetch_article_details_for_topic_search(self, url, journal_name):
        response = None
        html = ""
        final_url = url
        try:
            logger.debug(f"{self.journal_type} {journal_name}: 抓取候选详情 {url}")
            response = self.session.get(url, timeout=30)
            logger.debug(f"{self.journal_type} {journal_name}: 详情HTTP {response.status_code} {url}")
            response.raise_for_status()
            html = response.text or ""
            final_url = getattr(response, "url", None) or url
        except Exception as e:
            logger.warning(f"{self.journal_type} detail requests failed, trying parser fallback if enabled: {url} - {e}")

        article = self._parse_article_detail_html(html, final_url, journal_name) if html else None
        if self._detail_needs_browser_fallback(article, html):
            try:
                browser_html = self._fetch_detail_html_with_browser_fast(url)
                browser_article = self._parse_article_detail_html(browser_html or "", url, journal_name)
                if browser_article and (
                    not article
                    or len(browser_article.get("abstract") or "") > len(article.get("abstract") or "")
                ):
                    article = browser_article
            except Exception as e:
                logger.warning(f"{self.journal_type} detail Playwright fallback failed: {url} - {e}")

        if not article:
            page_title = ""
            if html:
                soup = BeautifulSoup(html, "html.parser")
                page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
            logger.warning(
                f"{self.journal_type} {journal_name}: 详情页未解析到标题，跳过 {url}; "
                f"final_url={final_url}; page_title={page_title[:120]}"
            )
            return None
        return article

    def _detail_needs_browser_fallback(self, article, html):
        if self.journal_type not in ("nature", "science", "plos"):
            return False
        if not html or is_challenge_page(html):
            return True
        if not article:
            return True
        return False

    def _fetch_detail_html_with_browser_fast(self, url):
        timeout = 12
        try:
            return _PLAYWRIGHT_EXECUTOR.submit(
                self._fetch_detail_html_with_browser_fast_in_worker,
                url,
            ).result(timeout=timeout)
        except Exception as e:
            logger.warning(f"{self.journal_type}: detail browser fallback timeout/failed, skip {url}: {e}")
            return None

    def _fetch_detail_html_with_browser_fast_in_worker(self, url):
        self._ensure_playwright_in_worker()
        browser = _PLAYWRIGHT_STATE.get("browser")
        if browser is None:
            return None
        logger.info(f"{self.journal_type}: detail Playwright quick fetch {url}")
        page = None
        with _DETAIL_BROWSER_LOCK:
            try:
                page = browser.new_page(
                    viewport={"width": 1366, "height": 768},
                    user_agent=self.session.headers.get("User-Agent") or self.user_agents[0],
                    locale="en-US",
                    timezone_id="Asia/Shanghai",
                )
                page.goto(url, wait_until="domcontentloaded", timeout=6000)
                time.sleep(0.8)
                for _ in range(2):
                    try:
                        page.evaluate("window.stop()")
                    except Exception:
                        pass
                    try:
                        html = page.content()
                        break
                    except Exception:
                        time.sleep(0.5)
                else:
                    logger.debug(f"{self.journal_type}: detail page still navigating, skip browser repair {url}")
                    return None
            except Exception as e:
                logger.debug(f"{self.journal_type}: detail Playwright quick fetch failed, skip {url}: {e}")
                return None
            finally:
                if page is not None:
                    try:
                        page.close()
                    except Exception:
                        pass
        if is_challenge_page(html):
            logger.debug(f"{self.journal_type}: detail page is challenge, skip browser repair {url}")
            return None
        return html

    def _parse_article_detail_html(self, html, url, journal_name):
        if not html:
            return None
        soup = BeautifulSoup(html, 'html.parser')

        title = self._first_meta_content(soup, [
            ("name", "citation_title"),
            ("property", "citation_title"),
            ("property", "og:title"),
            ("name", "dc.Title"),
            ("name", "dc.title"),
            ("name", "twitter:title"),
        ])
        if not title:
            title_node = soup.select_one("h1.article-header__title, h1.article-title, h1.title, h1")
            if title_node:
                title = title_node.get_text(" ", strip=True)
        if not title and soup.title:
            title = self._clean_html_title(soup.title.get_text(" ", strip=True))

        abstract = self._first_meta_content(soup, [
            ("name", "citation_abstract"),
            ("property", "citation_abstract"),
            ("name", "dc.Description"),
            ("name", "dc.description"),
            ("property", "og:description"),
            ("name", "description"),
        ])
        if not abstract:
            for selector in (
                "section#abstract",
                "div#abstract",
                "section.abstract",
                "div.abstract",
                "div.abstract.author",
                "section[aria-labelledby*='abstract' i]",
                "div[class*='Abstract' i]",
                "section[class*='Abstract' i]",
                "div[class*='abstract' i]",
                "section[class*='abstract' i]",
            ):
                abstract_node = soup.select_one(selector)
                if abstract_node:
                    abstract = abstract_node.get_text(" ", strip=True)
                    break
        abstract = self._clean_abstract_text(abstract)

        date_value = None
        date_text = self._first_meta_content(soup, [
            ("name", "citation_publication_date"),
            ("name", "dc.Date"),
            ("name", "dc.date"),
            ("property", "article:published_time"),
            ("name", "prism.publicationDate"),
        ])
        if date_text:
            try:
                date_value = dateparser.parse(date_text).date()
            except Exception:
                date_value = None

        doi = self._first_meta_content(soup, [
            ("name", "citation_doi"),
            ("property", "citation_doi"),
            ("name", "dc.Identifier"),
            ("name", "dc.identifier"),
        ])
        if doi and doi.lower().startswith("doi:"):
            doi = doi[4:].strip()
        if not doi:
            match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", html + " " + url, re.I)
            if match:
                doi = match.group(0).rstrip('.,;)"\'').strip()

        authors = []
        for tag in soup.find_all("meta", attrs={"name": "citation_author"}):
            value = tag.get("content", "").strip()
            if value:
                authors.append(value)

        if not title:
            return None
        return {
            'title': title,
            'url': url,
            'abstract': abstract,
            'date': date_value,
            'doi': doi,
            'type': 'topic_search',
            'journal': journal_name,
            'authors': "; ".join(authors)
        }

    def _first_meta_content(self, soup, attrs_list):
        for attr_name, attr_value in attrs_list:
            tag = soup.find("meta", attrs={attr_name: attr_value})
            if tag:
                value = tag.get("content", "").strip()
                if value:
                    return value
        return ""

    def _clean_html_title(self, title):
        title = clean_metadata_text(title)
        title = re.sub(r"\s*[\-|]\s*(Cell|ScienceDirect|Elsevier|Nature|SpringerLink|Wiley Online Library)\s*$", "", title, flags=re.I)
        return title.strip()

    def _clean_abstract_text(self, abstract):
        abstract = clean_metadata_text(abstract)
        abstract = re.sub(r"^(abstract|summary)\s*[:.-]?\s*", "", abstract, flags=re.I).strip()
        return abstract

    @staticmethod
    def _publisher_antibot_status_code(status_code):
        """HTTP status codes that should immediately stop publisher access."""
        try:
            value = int(status_code)
        except Exception:
            return False

        # 403/429 are the common cases. 401/406/418 are also frequently
        # returned by publisher WAF / bot-control systems.
        return value in {
            401,
            403,
            406,
            418,
            429,
        }

    @staticmethod
    def _publisher_antibot_html(html):
        """Detect common publisher/WAF challenge pages."""
        text = str(html or "").lower()

        if is_challenge_page(text):
            return True

        markers = (
            "verify you are human",
            "verify that you are human",
            "checking if the site connection is secure",
            "checking your browser",
            "enable javascript and cookies to continue",
            "please enable cookies",
            "access denied",
            "request blocked",
            "unusual traffic",
            "automated requests",
            "robot check",
            "captcha",
            "cloudflare ray id",
            "akamai",
            "imperva",
            "incapsula",
            "bot detection",
            "bot protection",
            "security challenge",
        )
        return any(marker in text for marker in markers)

    def _publisher_article_url(self, article):
        """Return the best article URL without performing a network request."""
        if not isinstance(article, dict):
            return ""

        for key in ("publisher_url", "link", "url"):
            value = str(article.get(key) or "").strip()
            if value.startswith(("http://", "https://")):
                return value

        doi = self._extract_doi_for_abstract(article)
        if doi:
            return f"https://doi.org/{doi}"

        return ""

    def _read_publisher_html_limited(self, response):
        """Read at most publisher_max_html_bytes from a publisher response."""
        chunks = []
        total = 0
        max_bytes = int(self.publisher_max_html_bytes)

        try:
            iterator = response.iter_content(
                chunk_size=64 * 1024,
                decode_unicode=False,
            )
        except Exception:
            raw = getattr(response, "content", b"") or b""
            if isinstance(raw, str):
                raw = raw.encode("utf-8", errors="ignore")
            raw = raw[:max_bytes]
            return raw.decode(
                getattr(response, "encoding", None) or "utf-8",
                errors="replace",
            )

        for chunk in iterator:
            if not chunk:
                continue

            remaining = max_bytes - total
            if remaining <= 0:
                break

            if len(chunk) > remaining:
                chunk = chunk[:remaining]

            chunks.append(chunk)
            total += len(chunk)

            if total >= max_bytes:
                break

        raw = b"".join(chunks)
        encoding = getattr(response, "encoding", None) or "utf-8"

        try:
            return raw.decode(encoding, errors="replace")
        except Exception:
            return raw.decode("utf-8", errors="replace")

    def _new_abstract_repair_publisher_session(self):
        """Create a zero-retry publisher Session for the current worker."""
        from requests.adapters import HTTPAdapter

        session = requests.Session()
        session.headers.update({
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        })
        adapter = HTTPAdapter(
            max_retries=0,
            pool_connections=4,
            pool_maxsize=4,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _get_thread_publisher_session(self):
        session = getattr(
            self._abstract_repair_local,
            "publisher_session",
            None,
        )
        if session is None:
            session = self._new_abstract_repair_publisher_session()
            self._abstract_repair_local.publisher_session = session
        return session

    def _get_thread_abstract_fetcher(self):
        fetcher = getattr(
            self._abstract_repair_local,
            "doi_fetcher",
            None,
        )
        if fetcher is None:
            fetcher = DoiAbstractFetcher(
                timeout=8,
            )
            self._abstract_repair_local.doi_fetcher = fetcher
        return fetcher

    def _fetch_publisher_article_once(self, article, journal_name):
        """Fetch one publisher/article page exactly once.

        This method intentionally has:
            * zero retry
            * no random backoff
            * no Playwright
            * immediate anti-bot detection

        It returns diagnostic metadata even when no abstract is obtained.
        """
        url = self._publisher_article_url(article)

        result = {
            "publisher_attempted": False,
            "publisher_status": "missing_url",
            "publisher_http_status": "",
            "publisher_url": url,
            "article": None,
        }

        if not url:
            return result

        result["publisher_attempted"] = True

        response = None
        try:
            logger.info(
                "%s %s: publisher abstract fetch once url=%s",
                self.journal_type,
                journal_name,
                url,
            )

            response = self._get_thread_publisher_session().get(
                url,
                timeout=self.publisher_abstract_timeout,
                allow_redirects=True,
                stream=True,
            )

            status_code = getattr(response, "status_code", None)
            result["publisher_http_status"] = (
                str(status_code)
                if status_code is not None
                else ""
            )
            result["publisher_url"] = (
                getattr(response, "url", None)
                or url
            )

            # Anti-bot HTTP codes: do not read/retry/browse. Fall back now.
            if self._publisher_antibot_status_code(status_code):
                result["publisher_status"] = "anti_bot"
                logger.warning(
                    "%s %s: publisher anti-bot HTTP %s -> DOI API immediately: %s",
                    self.journal_type,
                    journal_name,
                    status_code,
                    result["publisher_url"],
                )
                return result

            # Other HTTP failures also fall back to DOI APIs, but are recorded
            # separately from explicit anti-bot responses.
            if status_code is not None and int(status_code) >= 400:
                result["publisher_status"] = f"http_{status_code}"
                logger.info(
                    "%s %s: publisher HTTP %s -> DOI API: %s",
                    self.journal_type,
                    journal_name,
                    status_code,
                    result["publisher_url"],
                )
                return result

            html = self._read_publisher_html_limited(response)

            # A WAF can return 200 with a challenge page.
            if self._publisher_antibot_html(html):
                result["publisher_status"] = "anti_bot"
                logger.warning(
                    "%s %s: publisher challenge page -> DOI API immediately: %s",
                    self.journal_type,
                    journal_name,
                    result["publisher_url"],
                )
                return result

            parsed = self._parse_article_detail_html(
                html,
                result["publisher_url"],
                journal_name,
            )

            if not parsed:
                result["publisher_status"] = "parse_failed"
                return result

            abstract = self._clean_abstract_text(
                parsed.get("abstract") or ""
            )
            parsed["abstract"] = abstract

            if not abstract:
                result["publisher_status"] = "no_abstract"
                result["article"] = parsed
                return result

            result["publisher_status"] = "success"
            result["article"] = parsed

            logger.info(
                "%s %s: publisher abstract repaired successfully: %s",
                self.journal_type,
                journal_name,
                result["publisher_url"],
            )
            return result

        except requests.Timeout:
            result["publisher_status"] = "timeout"
            logger.info(
                "%s %s: publisher timeout -> DOI API: %s",
                self.journal_type,
                journal_name,
                url,
            )
            return result

        except requests.RequestException as exc:
            result["publisher_status"] = "request_error"
            logger.info(
                "%s %s: publisher request failed -> DOI API: %s - %s",
                self.journal_type,
                journal_name,
                url,
                exc,
            )
            return result

        except Exception as exc:
            result["publisher_status"] = "error"
            logger.warning(
                "%s %s: publisher parse/fetch error -> DOI API: %s - %s",
                self.journal_type,
                journal_name,
                url,
                exc,
            )
            return result

        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    @staticmethod
    def _merge_repaired_metadata(original, repaired):
        """Fill useful metadata while preserving already-known values."""
        result = dict(original or {})
        repaired = repaired or {}

        repaired_url = str(
            repaired.get("link")
            or repaired.get("url")
            or ""
        ).strip()

        if repaired_url and not str(result.get("link") or "").strip():
            result["link"] = repaired_url

        for field in (
            "title",
            "date",
            "doi",
            "authors",
            "journal",
            "article_type",
        ):
            current = result.get(field)

            if current is not None and str(current).strip():
                continue

            value = repaired.get(field)

            if field == "article_type" and not value:
                value = repaired.get("type")

            if value is not None and str(value).strip():
                result[field] = value

        return result

    def repair_abstract_publisher_then_doi(self, article, journal_name):
        """Shared abstract repair strategy for ALL journal types.

        Order:
            1. publisher/article page, exactly one HTTP attempt
            2. if publisher is blocked, unavailable, or has no abstract:
               doi_abstract.py
                 -> Crossref DOI API
                 -> Europe PMC
                 -> OpenAlex
                 -> Semantic Scholar

        Anti-bot behavior:
            403 / 429 / WAF challenge / CAPTCHA
            -> no publisher retry
            -> no Playwright
            -> immediate DOI API fallback
        """
        if not isinstance(article, dict):
            return None

        original_abstract = str(
            article.get("abstract") or ""
        ).strip()

        if original_abstract:
            result = dict(article)
            result.update({
                "abstract_repaired": False,
                "abstract_repair_status": "existing",
                "abstract_repair_method": "existing",
                "publisher_attempted": False,
                "publisher_status": "not_needed",
                "publisher_http_status": "",
                "publisher_url": "",
                "doi_abstract_attempted": False,
            })
            return result

        result = dict(article)

        # --------------------------------------------------------------
        # Stage 1: publisher/article page exactly once.
        # --------------------------------------------------------------
        publisher = self._fetch_publisher_article_once(
            article,
            journal_name,
        )

        result["publisher_attempted"] = bool(
            publisher.get("publisher_attempted")
        )
        result["publisher_status"] = str(
            publisher.get("publisher_status") or ""
        )
        result["publisher_http_status"] = str(
            publisher.get("publisher_http_status") or ""
        )
        result["publisher_url"] = str(
            publisher.get("publisher_url") or ""
        )

        publisher_article = publisher.get("article") or {}
        result = self._merge_repaired_metadata(
            result,
            publisher_article,
        )

        publisher_abstract = str(
            publisher_article.get("abstract") or ""
        ).strip()

        if publisher_abstract:
            result["abstract"] = publisher_abstract
            result["abstract_repaired"] = True
            result["abstract_repair_status"] = "repaired"
            result["abstract_repair_method"] = "publisher"
            result["abstract_source"] = "publisher"

            publisher_host = urlparse(
                result.get("publisher_url") or ""
            ).netloc.lower()

            if publisher_host:
                result["abstract_source"] = (
                    f"publisher:{publisher_host}"
                )

            result["doi_abstract_attempted"] = False
            return result

        # --------------------------------------------------------------
        # Stage 2: DOI metadata APIs.
        # --------------------------------------------------------------
        result["doi_abstract_attempted"] = True

        doi_repaired = self.repair_abstract_by_doi(
            result,
            journal_name,
        )

        doi_abstract = str(
            (doi_repaired or {}).get("abstract") or ""
        ).strip()

        if doi_abstract:
            merged = self._merge_repaired_metadata(
                result,
                doi_repaired,
            )
            merged["abstract"] = doi_abstract
            merged["abstract_repaired"] = True
            merged["abstract_repair_status"] = "repaired"
            merged["abstract_repair_method"] = "doi_api"
            merged["abstract_source"] = str(
                (doi_repaired or {}).get(
                    "abstract_source"
                )
                or (doi_repaired or {}).get("source")
                or "doi_api"
            ).strip()
            merged["doi_abstract_attempted"] = True
            return merged

        # Keep publisher diagnostics even when both stages fail.
        result["abstract"] = ""
        result["abstract_repaired"] = False
        result["abstract_repair_status"] = "not_found"
        result["abstract_repair_method"] = "none"
        result["abstract_source"] = ""
        result["doi_abstract_attempted"] = True
        return result

    def _extract_doi_for_abstract(self, article):
        """Extract a DOI from article metadata without visiting any webpage."""
        if not isinstance(article, dict):
            return ""

        for value in (
            article.get("doi"),
            article.get("url"),
            article.get("link"),
        ):
            text = str(value or "").strip()
            if not text:
                continue

            normalized = DoiAbstractFetcher.normalize_doi(text)
            if normalized.startswith("10.") and "/" in normalized:
                return normalized

            match = re.search(
                r"10\.\d{4,9}/[-._;()/:A-Z0-9]+",
                text,
                flags=re.I,
            )
            if match:
                return DoiAbstractFetcher.normalize_doi(
                    match.group(0).rstrip('.,;)"\'')
                )

        return ""

    def repair_abstract_by_doi(self, article, journal_name):
        """Repair a missing abstract via the DOI metadata API chain.

        This is the SECOND-stage fallback used by
        repair_abstract_publisher_then_doi().

        This method is intentionally platform-agnostic and is used by
        Nature / PLOS / Science / Cell / OTHER.

        It NEVER follows doi.org to a publisher page and NEVER scrapes a
        publisher page for abstract repair.

        Source order is controlled only by parser/doi_abstract.py:
            Crossref DOI API
            -> Europe PMC
            -> OpenAlex
            -> Semantic Scholar
        """
        if not isinstance(article, dict):
            return None

        if str(article.get("abstract") or "").strip():
            result = dict(article)
            result["abstract_repaired"] = False
            return result

        doi = self._extract_doi_for_abstract(article)
        if not doi:
            logger.debug(
                "%s %s: DOI abstract repair skipped; missing DOI title=%s",
                self.journal_type,
                journal_name,
                str(article.get("title") or "")[:120],
            )
            return None

        try:
            fetched = self._get_thread_abstract_fetcher().fetch_by_doi(doi)
        except Exception as exc:
            logger.warning(
                "%s %s: DOI abstract API repair failed doi=%s: %s",
                self.journal_type,
                journal_name,
                doi,
                exc,
            )
            return None

        if not fetched:
            return None

        abstract = str(fetched.get("abstract") or "").strip()
        if not abstract:
            return None

        result = dict(article)
        result["doi"] = result.get("doi") or doi
        result["abstract"] = abstract
        result["abstract_repaired"] = True
        result["abstract_source"] = str(
            fetched.get("source") or ""
        ).strip()

        # Preserve the platform/Crossref metadata already collected.
        # Only fill fields that are currently empty.
        for field in ("title", "authors", "journal", "date"):
            if str(result.get(field) or "").strip():
                continue
            value = fetched.get(field)
            if value is not None and str(value).strip():
                result[field] = value

        if not str(result.get("link") or "").strip():
            fetched_url = str(fetched.get("url") or "").strip()
            if fetched_url:
                result["link"] = fetched_url

        result["source"] = result.get("source") or "crossref"
        return result

    def repair_article_from_url(self, article, journal_name):
        url = (
            article.get("link")
            or article.get("url")
            or (f"https://doi.org/{article.get('doi')}" if article.get("doi") else "")
        )
        if not url:
            return None
        repaired = self.fetch_article_details_for_topic_search(url, journal_name)
        if not repaired:
            return None
        result = dict(article)
        if repaired.get("url"):
            result["link"] = repaired.get("url")
        for field in ("title", "abstract", "date", "doi", "authors"):
            value = repaired.get(field)
            if value is not None and str(value).strip():
                result[field] = value
        if repaired.get("type"):
            result["article_type"] = repaired.get("type")
        result["source"] = result.get("source") or "detail_repair"
        return result

    def scrape_journal_topic_search_stream(self, journal_name, base_url, start_date, end_date, callback):
        keywords = self.get_topic_search_keywords()
        max_pages = self.get_topic_search_max_pages()
        seen_urls = set()
        seen_dois = set()
        all_articles = []
        logger.info(f"{self.journal_type} {journal_name}: topic_search stream 使用 {len(keywords)} 个关键词，每个关键词最多 {max_pages} 页")

        for keyword in keywords:
            keyword_candidates = []
            for page in range(1, max_pages + 1):
                search_url = self.build_topic_search_url(journal_name, base_url, keyword, page)
                if not search_url:
                    continue
                try:
                    logger.info(f"{self.journal_type} {journal_name}: 搜索关键词 '{keyword}' 第{page}页 URL={search_url}")
                    search_html = self.get_search_html_with_fallback(search_url, timeout=15)
                    if not search_html:
                        break
                    page_urls = self.extract_candidate_urls_from_search_page(search_html, base_url)
                    logger.info(f"{self.journal_type} {journal_name}: 搜索页候选 {len(page_urls)} 个 keyword='{keyword}' page={page}")
                    if not page_urls:
                        self._save_zero_candidate_search_debug_html(journal_name, keyword, page, search_url, search_html)
                        lower_html = (search_html or '').lower()
                        if (
                            is_challenge_page(search_html)
                            or '403' in lower_html
                            or 'access denied' in lower_html
                            or 'forbidden' in lower_html
                        ):
                            logger.warning(
                                f"{self.journal_type} {journal_name}: 搜索页候选为0，"
                                f"reason=搜索结果页疑似被拦截或不是正常结果页 url={search_url}"
                            )
                    if should_stop_keyword_paging(len(page_urls)):
                        break
                    new_count = 0
                    for url in page_urls:
                        deduped = dedupe_candidate_urls([{'url': url, 'matched_keyword': keyword}])
                        if not deduped:
                            continue
                        normalized_url = deduped[0]['url']
                        if normalized_url in seen_urls:
                            continue
                        seen_urls.add(normalized_url)
                        keyword_candidates.append(deduped[0])
                        new_count += 1
                    logger.info(f"{self.journal_type} {journal_name}: keyword='{keyword}' page={page} 新增候选 {new_count} 个")
                    time.sleep(random.uniform(0.5, 1.5))
                except Exception as e:
                    logger.warning(f"{self.journal_type} {journal_name}: 搜索关键词失败 {keyword}: {e}")
                    break

            if not keyword_candidates:
                logger.info(f"{self.journal_type} {journal_name}: 关键词 '{keyword}' 无新增候选")
                continue

            keyword_articles = []
            detail_failed = 0
            date_filtered = 0
            for candidate in self._progress(keyword_candidates, total=len(keyword_candidates), desc=f"{self.journal_type} {journal_name} {keyword} 详情"):
                article = self.fetch_article_details_for_topic_search(candidate['url'], journal_name)
                if not article:
                    detail_failed += 1
                    continue
                article['matched_keyword'] = candidate.get('matched_keyword', keyword)
                doi = str(article.get('doi') or '').strip().lower()
                if doi:
                    if doi in seen_dois:
                        continue
                    seen_dois.add(doi)
                if article.get('date') and not self._is_date_in_range(article['date'], start_date, end_date):
                    date_filtered += 1
                    logger.info(
                        f"{self.journal_type} {journal_name}: 过滤文章 "
                        f"reason=日期超出范围 "
                        f"article_date={article.get('date')} "
                        f"range={start_date}..{end_date} "
                        f"title={str(article.get('title', ''))[:100]} "
                        f"url={article.get('url', candidate.get('url', ''))}"
                    )
                    continue
                keyword_articles.append(article)

            logger.info(
                f"{self.journal_type} {journal_name}: 关键词 '{keyword}' 详情抓取统计 "
                f"{summarize_counts(success=len(keyword_articles), detail_failed=detail_failed, date_filtered=date_filtered)}"
            )
            if keyword_articles:
                all_articles.extend(keyword_articles)
                callback(keyword_articles)

        return all_articles

    def _save_zero_candidate_search_debug_html(self, journal_name, keyword, page, search_url, html):
        try:
            safe = re.sub(r'[^A-Za-z0-9_.-]+', '_', f"{self.journal_type}_{journal_name}_{keyword}_{page}")[:120]
            debug_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'exports', 'debug')
            os.makedirs(debug_dir, exist_ok=True)
            path = os.path.join(debug_dir, f"zero_candidates_{safe}.html")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(f"<!-- search_url: {search_url} -->\n")
                f.write(html or '')
            logger.info(f"{self.journal_type} {journal_name}: 搜索页候选为0，debug HTML已保存: {path}")
        except Exception as e:
            logger.debug(f"{self.journal_type} {journal_name}: 保存0候选debug HTML失败: {e}")

    def scrape_journal_topic_search(self, journal_name, base_url, start_date, end_date):
        articles = []
        self.scrape_journal_topic_search_stream(
            journal_name,
            base_url,
            start_date,
            end_date,
            callback=lambda batch: articles.extend(batch),
        )
        return articles

        keywords = self.get_topic_search_keywords()
        max_pages = self.get_topic_search_max_pages()
        candidates = []
        logger.info(f"{self.journal_type} {journal_name}: topic_search 使用 {len(keywords)} 个关键词，每个关键词最多 {max_pages} 页")
        for keyword in keywords:
            keyword_before = len(candidates)
            for page in range(1, max_pages + 1):
                search_url = self.build_topic_search_url(journal_name, base_url, keyword, page)
                if not search_url:
                    continue
                try:
                    used_browser_fallback = False
                    logger.info(f"{self.journal_type} {journal_name}: 搜索关键词 '{keyword}' 第{page}页 URL={search_url}")
                    response = self.session.get(search_url, timeout=15)
                    logger.info(f"{self.journal_type} {journal_name}: 搜索HTTP {response.status_code} keyword='{keyword}' page={page}")
                    if response.status_code != 200:
                        logger.warning(f"搜索页HTTP {response.status_code}: {search_url}")
                        fallback_html = self.get_search_page_with_browser(search_url)
                        used_browser_fallback = True
                        if fallback_html:
                            search_html = fallback_html
                        else:
                            continue
                    else:
                        search_html = response.text
                    if is_challenge_page(search_html) and not used_browser_fallback:
                        logger.warning(f"{self.journal_type} {journal_name}: 搜索页返回challenge，尝试Playwright fallback")
                        fallback_html = self.get_search_page_with_browser(search_url)
                        used_browser_fallback = True
                        if fallback_html:
                            search_html = fallback_html
                    page_urls = self.extract_candidate_urls_from_search_page(search_html, base_url)
                    if not page_urls and not is_challenge_page(search_html) and not used_browser_fallback:
                        logger.info(f"{self.journal_type} {journal_name}: requests未解析到候选，尝试Playwright fallback验证")
                        fallback_html = self.get_search_page_with_browser(search_url)
                        used_browser_fallback = True
                        if fallback_html:
                            fallback_urls = self.extract_candidate_urls_from_search_page(fallback_html, base_url)
                            if fallback_urls:
                                logger.info(f"{self.journal_type} {journal_name}: Playwright fallback解析到候选 {len(fallback_urls)} 个")
                                page_urls = fallback_urls
                    logger.info(f"{self.journal_type} {journal_name}: 搜索页候选 {len(page_urls)} 个 keyword='{keyword}' page={page}")
                    if should_stop_keyword_paging(len(page_urls)):
                        logger.info(f"{self.journal_type} {journal_name}: keyword='{keyword}' page={page} 无候选，停止该关键词后续分页")
                        break
                    for url in page_urls:
                        candidates.append({'url': url, 'matched_keyword': keyword})
                    time.sleep(random.uniform(0.5, 1.5))
                except Exception as e:
                    logger.warning(f"搜索关键词失败 {keyword}: {e}")
                    continue
            logger.info(f"{self.journal_type} {journal_name}: 关键词 '{keyword}' 累计新增候选 {len(candidates) - keyword_before} 个")

        raw_candidate_count = len(candidates)
        candidates = dedupe_candidate_urls(candidates)
        logger.info(f"{self.journal_type} {journal_name}: topic_search 候选统计 {summarize_counts(raw=raw_candidate_count, deduped=len(candidates))}")
        articles = []
        date_filtered = 0
        detail_failed = 0
        progress_desc = f"{self.journal_type} {journal_name} 详情"
        for idx, candidate in enumerate(self._progress(candidates, total=len(candidates), desc=progress_desc), 1):
            article = self.fetch_article_details_for_topic_search(candidate['url'], journal_name)
            if not article:
                detail_failed += 1
                continue
            article['matched_keyword'] = candidate.get('matched_keyword', '')
            if article.get('date') and not self._is_date_in_range(article['date'], start_date, end_date):
                date_filtered += 1
                logger.info(f"{self.journal_type} {journal_name}: 日期不在范围内，跳过 {article.get('date')} {article.get('title', '')[:80]}")
                continue
            articles.append(article)

        logger.info(f"{self.journal_type} {journal_name}: 详情抓取统计 {summarize_counts(success=len(articles), detail_failed=detail_failed, date_filtered=date_filtered)}")
        before_topic_filter = len(articles)
        articles = self.filter_topic_candidates(articles)
        logger.info(f"{self.journal_type} {journal_name}: 关键词预筛统计 {summarize_counts(before=before_topic_filter, after=len(articles))}")
        return articles

    def _init_playwright(self):
        try:
            _PLAYWRIGHT_EXECUTOR.submit(self._ensure_playwright_in_worker).result(timeout=90)
            self.playwright = _PLAYWRIGHT_STATE.get("playwright")
            self.browser = _PLAYWRIGHT_STATE.get("browser")
            self.page = _PLAYWRIGHT_STATE.get("page")
        except Exception as e:
            logger.error(f"{self.journal_type}: Playwright init failed: {e}")
            self.page = None

    def _ensure_playwright_in_worker(self):
        with _PLAYWRIGHT_STATE_LOCK:
            if _PLAYWRIGHT_STATE.get("page") is not None:
                return
            from playwright.sync_api import sync_playwright
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page(
                viewport={"width": 1920, "height": 1080},
                user_agent=random.choice(self.user_agents)
            )
            _PLAYWRIGHT_STATE["playwright"] = playwright
            _PLAYWRIGHT_STATE["browser"] = browser
            _PLAYWRIGHT_STATE["page"] = page
            logger.info(f"{self.journal_type}: shared Playwright initialized")

    def fetch_html_with_playwright(self, url, wait_selector=None, max_wait=60, settle_seconds=0):
        timeout = max(90, int(max_wait) + 90)
        return _PLAYWRIGHT_EXECUTOR.submit(
            self._fetch_html_with_playwright_in_worker,
            url,
            wait_selector,
            max_wait,
            settle_seconds,
        ).result(timeout=timeout)

    def _fetch_html_with_playwright_in_worker(self, url, wait_selector=None, max_wait=60, settle_seconds=0):
        self._ensure_playwright_in_worker()
        page = _PLAYWRIGHT_STATE.get("page")
        if page is None:
            return None
        logger.info(f"{self.journal_type}: Playwright fetch {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if max_wait:
            try:
                self.wait_for_page_load(page, max_wait)
            except Exception as e:
                logger.debug(f"{self.journal_type}: Playwright wait skipped/failed: {e}")
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=20000)
            except Exception:
                logger.warning(f"{self.journal_type}: Playwright selector wait timed out: {wait_selector}")
        if settle_seconds:
            time.sleep(settle_seconds)
        return page.content()

    def close_browser(self):
        try:
            _PLAYWRIGHT_EXECUTOR.submit(self._close_playwright_in_worker).result(timeout=30)
            self.page = None
            self.browser = None
            self.playwright = None
            logger.info(f"{self.journal_type}: Playwright resources cleaned")
        except Exception as e:
            logger.warning(f"{self.journal_type}: Playwright cleanup failed: {e}")

    def _close_playwright_in_worker(self):
        with _PLAYWRIGHT_STATE_LOCK:
            page = _PLAYWRIGHT_STATE.get("page")
            browser = _PLAYWRIGHT_STATE.get("browser")
            playwright = _PLAYWRIGHT_STATE.get("playwright")
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            if browser:
                browser.close()
            if playwright:
                playwright.stop()
            _PLAYWRIGHT_STATE["page"] = None
            _PLAYWRIGHT_STATE["browser"] = None
            _PLAYWRIGHT_STATE["playwright"] = None

    def wait_for_page_load(self, page, max_wait=60):
        """
        等待Playwright页面加载完成
        检测Cloudflare等反爬页面
        """

        if not page:
            return False
        start_time = time.time()
        consecutive_anti_bot = 0
        anti_bot_phrases = [
            'just a moment',
            'please wait',
            'checking your browser',
            'cloudflare',
            'ddos protection',
            'access denied',
            'blocked',
            'security check',
            'ray id',
            'performance & security',
            'everything we learned from powering',
            'powering 20% of the internet'
        ]
        while time.time() - start_time < max_wait:
            try:
                # 获取标题
                title = (
                    page.title()
                    .lower()
                )
                # 获取HTML
                page_source = (
                    page.content()
                    .lower()
                )
                is_anti_bot = any(
                    phrase in title
                    or phrase in page_source
                    for phrase in anti_bot_phrases
                )
                if is_anti_bot:
                    consecutive_anti_bot += 1
                    elapsed = int(
                        time.time()-start_time
                    )
                    logger.info(
                        f"检测到反爬页面，继续等待 "
                        f"{elapsed}s "
                        f"(第{consecutive_anti_bot}次)"
                    )
                    # 等待Cloudflare JS challenge
                    time.sleep(5)
                    continue
                else:
                    consecutive_anti_bot = 0

                # 页面内容检查

                if len(page_source) > 1000:

                    keywords = [
                        'science',
                        'research',
                        'article',
                        'doi'
                    ]

                    if any(
                        k in page_source
                        for k in keywords
                    ):

                        logger.info(
                            "页面加载完成"
                        )
                        return True
                time.sleep(2)
            except Exception as e:
                logger.warning(
                    f"等待页面加载错误: {e}"
                )
                time.sleep(3)
        logger.warning(
            f"页面加载超时 ({max_wait}s)"
        )
        return False
    
    def get_page_with_retry(self, url, max_retries=3, timeout=60, use_browser_fallback=True):
        """增强的请求方法"""
        # 第一阶段：使用requests方式，最多重试3次
        for attempt in range(max_retries):
            try:
                # 轮换User-Agent
                if hasattr(self, 'user_agents'):
                    user_agent = random.choice(self.user_agents)
                    self.session.headers['User-Agent'] = user_agent
                elif hasattr(self, 'science_user_agents'):
                    user_agent = random.choice(self.science_user_agents)
                    self.session.headers['User-Agent'] = user_agent
                elif hasattr(self, 'cell_user_agents'):
                    user_agent = random.choice(self.cell_user_agents)
                    self.session.headers['User-Agent'] = user_agent
                
                # 增加随机延迟避免被检测
                if attempt > 0:
                    delay = random.uniform(5, 15) * (attempt + 1)  # 更长的延迟
                    logger.info(f"Requests第{attempt + 1}次尝试前等待 {delay:.1f} 秒...")
                    time.sleep(delay)
                
                logger.info(f"requests方式访问 {url} (第 {attempt + 1} 次)")
                response = self.session.get(url, timeout=timeout)
                
                if response.status_code == 200:
                    logger.info(f"成功获取页面: {url}")
                    return response
                elif response.status_code == 403:
                    logger.warning(f"收到403错误 (第 {attempt + 1} 次): {url}")
                    if attempt < max_retries - 1:
                        # 403错误时等待更长时间
                        time.sleep(random.uniform(10, 20))  # 403错误更长等待
                        continue
                else:
                    logger.warning(f"HTTP {response.status_code}: {url}")
                    
            except Exception as e:
                logger.warning(f"requests请求失败 (第 {attempt + 1} 次): {e}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(5, 12))  # 更长的错误恢复时间
        
        # 第二阶段：如果requests失败，使用Playwright备选方案
        if use_browser_fallback:
            logger.info(f"Requests failed, trying Playwright fallback: {url}")
            try:
                page_source = self.fetch_html_with_playwright(url, max_wait=30, settle_seconds=5)
                if page_source and "403" not in page_source and "Forbidden" not in page_source and len(page_source) > 1000:
                    logger.info(f"Playwright fetched page: {url}")

                    class BrowserResponse:
                        def __init__(self, text, status_code=200):
                            self.text = text
                            self.status_code = status_code
                            self.content = text.encode("utf-8")

                    return BrowserResponse(page_source)
                logger.warning(f"Playwright page invalid: {url}")
            except Exception as e:
                logger.error(f"Playwright fallback failed: {e}")
        return None

    def _load_is_journal_config(self, journal_type):
        """返回内置解析辅助配置，不再读取 journals_config/*.json。"""
        return {}
    def cleanup(self):
        """清理Playwright和requests资源"""
        self.close_browser()
        try:
            if self.session:
                self.session.close()
        except Exception as e:
            logger.warning(f"{self.journal_type}: session关闭失败: {e}")

        try:
            if getattr(self, "publisher_session", None):
                self.publisher_session.close()
        except Exception as e:
            logger.warning(f"{self.journal_type}: publisher_session关闭失败: {e}")
