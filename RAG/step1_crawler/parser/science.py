# -*- coding: utf-8 -*-
import logging
import re

from .base import BaseParser
from .crossref_metadata import CrossrefMetadataFetcher


logger = logging.getLogger(__name__)


class ScienceParser(BaseParser):
    """Science parser using the same Crossref-only flow as NewJournalParser.

    The public class and method names are preserved for main.py compatibility.
    Science.org archive/search/detail/browser access is disabled so normal runs
    are driven by ISSN -> Crossref -> local keyword filter -> LLM callback.
    """

    def __init__(self, paper_agent=None):
        super().__init__("science", paper_agent)
        self.current_journal_info = {}
        self.issue_result_handler = None
        self.metadata_fetcher = CrossrefMetadataFetcher(try_all_issns=False)
        self.browser_manager = None

    def set_current_journal_info(self, journal_info):
        self.current_journal_info = journal_info or {}

    def set_issue_result_handler(self, handler):
        self.issue_result_handler = handler

    def should_use_topic_search(self):
        return True

    def scrape_journal(
        self,
        journal_name,
        base_url,
        start_date,
        end_date,
    ):
        """Compatibility entry backed by the streaming Crossref path."""
        if self.issue_result_handler:
            self.scrape_journal_stream(
                journal_name,
                base_url,
                start_date,
                end_date,
                callback=lambda batch: self.issue_result_handler(
                    batch,
                    "Crossref metadata",
                ),
            )
            return []

        articles = []

        self.scrape_journal_stream(
            journal_name,
            base_url,
            start_date,
            end_date,
            callback=lambda batch: articles.extend(batch),
        )

        return articles


    def scrape_journal_stream(
        self,
        journal_name,
        base_url,
        start_date,
        end_date,
        callback=None,
    ):
        """Stream Crossref metadata in bounded batches."""
        issns = self._get_current_issns()

        if not issns:
            logger.info(
                "Science %s: CSV missing ISSN/EISSN; Crossref skipped",
                journal_name,
            )
            return 0

        config = getattr(
            self.paper_agent,
            "config",
            {},
        ) if self.paper_agent else {}

        try:
            stream_batch_size = max(
                1,
                int(
                    config.get(
                        "CROSSREF_STREAM_BATCH_SIZE",
                        200,
                    )
                ),
            )
        except Exception:
            stream_batch_size = 200

        logger.info(
            "Science %s: Crossref streaming "
            "issn=%s batch_size=%s range=%s..%s",
            journal_name,
            ",".join(issns),
            stream_batch_size,
            start_date,
            end_date,
        )

        emitted = 0
        date_filtered = 0

        def handle_crossref_batch(rows):
            nonlocal emitted
            nonlocal date_filtered

            normalized = []

            for row in rows or []:
                article_date = row.get("date")

                if (
                    article_date
                    and not self._is_date_in_range(
                        article_date,
                        start_date,
                        end_date,
                    )
                ):
                    date_filtered += 1
                    continue

                article = self._normalize_article(
                    row,
                    journal_name,
                )
                article["quality_score"] = (
                    self.validate_article(article)
                )
                normalized.append(article)

            if not normalized:
                return

            emitted += len(normalized)

            if callback:
                callback(normalized)

        total_crossref = self.metadata_fetcher.fetch_by_issn_stream(
            issns=issns,
            start_date=start_date,
            end_date=end_date,
            keywords=None,
            journal_name=journal_name,
            callback=handle_crossref_batch,
            batch_size=stream_batch_size,
        )

        for item in self._iter_keyword_stats():
            logger.info(
                "Science %s: Crossref issn=%s keyword='%s' "
                "fetched=%s added=%s pages=%s windows=%s stop=%s",
                journal_name,
                item.get("issn", ""),
                item.get("keyword", "") or "ALL",
                item.get("fetched", 0),
                item.get("added", 0),
                item.get("pages", 0),
                item.get("windows", 0),
                item.get("stop_reason", ""),
            )

        logger.info(
            "Science %s: Crossref stream complete "
            "unique=%s metadata_emitted=%s date_filtered=%s",
            journal_name,
            total_crossref,
            emitted,
            date_filtered,
        )

        return emitted


    def scrape_journal_topic_search(self, journal_name, base_url, start_date, end_date):
        return self.scrape_journal(journal_name, base_url, start_date, end_date)

    def scrape_journal_topic_search_stream(self, journal_name, base_url, start_date, end_date, callback):
        return self.scrape_journal_stream(journal_name, base_url, start_date, end_date, callback)

    def scrape_topic_search(self, journal_name, keywords, max_pages=1):
        logger.info(f"Science {journal_name}: scrape_topic_search skipped; parser is Crossref-only")
        return []

    # Interface compatibility: publisher/web search is intentionally disabled.
    def build_topic_search_url(self, journal_name, base_url, keyword, page=1):
        return None

    def extract_candidate_urls_from_search_page(self, html, base_url):
        return []

    def fetch_article_details_for_topic_search(self, url, journal_name):
        return None

    def get_search_html_with_fallback(self, search_url, timeout=60):
        return None

    def get_search_page_with_browser(self, search_url):
        return None

    def _get_search_page_with_browser(self, search_url):
        return None

    def _get_search_page_with_selenium(self, search_url):
        return None

    def _ensure_science_search_no_retry(self):
        return None

    def _science_selenium_warmup(self, driver):
        return None

    def _selenium_warmup(self):
        return None

    def close(self):
        try:
            if self.session:
                self.session.close()
        except Exception as e:
            logger.warning(f"Science session close failed: {e}")

    def _scrape_crossref_batch(self, journal_name, start_date, end_date):
        issns = self._get_current_issns()
        if not issns:
            logger.info(f"Science {journal_name}: CSV missing ISSN/EISSN; Crossref skipped")
            return []

        logger.info(
            f"Science {journal_name}: Crossref only issn={','.join(issns)} "
            f"keywords=disabled range={start_date}..{end_date}"
        )
        rows = self.metadata_fetcher.fetch_by_issn(
            issns=issns,
            start_date=start_date,
            end_date=end_date,
            keywords=None,
            journal_name=journal_name,
        )
        if not rows:
            logger.info(f"Science {journal_name}: Crossref returned 0 articles")
            return []

        deduped = self._dedupe_metadata_by_doi(rows)
        date_kept = []
        date_filtered = 0
        for row in deduped:
            article_date = row.get("date")
            if article_date and not self._is_date_in_range(article_date, start_date, end_date):
                date_filtered += 1
                continue
            date_kept.append(self._normalize_article(row, journal_name))

        for article in date_kept:
            article["quality_score"] = self.validate_article(article)

        for item in self._iter_keyword_stats():
            logger.info(
                f"Science {journal_name}: keyword='{item.get('keyword', '') or 'ALL'}' "
                f"fetched={item.get('fetched', 0)} added={item.get('added', 0)}"
            )
        logger.info(
            f"Science {journal_name}: Crossref batch candidate={len(rows)}, "
            f"deduped={len(deduped)}, date_filtered={date_filtered}, metadata_kept={len(date_kept)}"
        )
        return date_kept

    def _get_current_issns(self):
        source_row = {}
        if isinstance(self.current_journal_info, dict):
            source_row = self.current_journal_info.get("source_row") or {}

        values = []
        for container in (self.current_journal_info or {}, source_row):
            for key, value in (container or {}).items():
                normalized_key = str(key or "").strip().lower().replace("-", "").replace("_", "")
                if normalized_key in ("issn", "eissn", "printissn", "onlineissn"):
                    values.append(value)

        issns = []
        for value in values:
            for part in re.split(r"[;,/|\s]+", str(value or "")):
                compact = part.strip().upper().replace("-", "")
                if re.match(r"^\d{7}[\dX]$", compact):
                    formatted = f"{compact[:4]}-{compact[4:]}"
                    if formatted not in issns:
                        issns.append(formatted)
        return issns

    def _iter_keyword_stats(self):
        stats = getattr(self.metadata_fetcher, "last_keyword_stats", [])
        if isinstance(stats, dict):
            for keyword, item in stats.items():
                row = dict(item or {})
                row.setdefault("keyword", keyword)
                yield row
            return
        if isinstance(stats, list):
            for item in stats:
                if isinstance(item, dict):
                    yield item

    def _dedupe_metadata_by_doi(self, rows):
        seen = set()
        deduped = []
        for row in rows or []:
            doi = str(row.get("doi") or "").strip().lower()
            if not doi or doi in seen:
                continue
            seen.add(doi)
            deduped.append(row)
        return deduped

    def _normalize_article(self, row, journal_name):
        article = dict(row or {})
        doi = str(article.get("doi") or "").strip()
        if doi:
            article["doi"] = doi
            article.setdefault("url", f"https://doi.org/{doi}")
        article.setdefault("journal", journal_name)
        article.setdefault("title", "")
        article.setdefault("abstract", "")
        article.setdefault("authors", "")
        article.setdefault("article_type", article.get("type", ""))
        article["source"] = article.get("source") or "crossref"
        return article

    def validate_article(self, article):
        if not article:
            return 0
        score = 0
        if article.get("title"):
            score += 20
        if article.get("doi"):
            score += 30
        if article.get("abstract"):
            score += 30
        if article.get("date"):
            score += 20
        return score
