# -*- coding: utf-8 -*-
import logging
import re

from .base import BaseParser
from .crossref_metadata import CrossrefMetadataFetcher


logger = logging.getLogger(__name__)


class CellParser(BaseParser):
    """Cell parser using the same Crossref-only flow as NewJournalParser.

    The class keeps the public parser interface and the issue callback hook used
    by main.py, but it no longer visits Cell archive, issue, search, or detail
    pages. LLM review/export remains in main.py.
    """

    def __init__(self, paper_agent=None):
        super().__init__("cell", paper_agent)
        self.current_journal_info = {}
        self.issue_result_handler = None
        self.metadata_fetcher = CrossrefMetadataFetcher(try_all_issns=False)

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
                "CELL %s: CSV missing ISSN/EISSN; Crossref skipped",
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
            "CELL %s: Crossref streaming "
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
                "CELL %s: Crossref issn=%s keyword='%s' "
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
            "CELL %s: Crossref stream complete "
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

    # Interface compatibility: publisher/web search is intentionally disabled.
    def build_topic_search_url(self, journal_name, base_url, keyword, page=1):
        return None

    def extract_candidate_urls_from_search_page(self, html, base_url):
        return []

    def fetch_article_details_for_topic_search(self, url, journal_name):
        doi = self._doi_from_value(url)
        if not doi:
            return None
        result = self.abstract_fetcher.fetch_by_doi(doi)
        if not result:
            return None
        return self._metadata_result_to_article(result, doi, journal_name)


    def get_search_page_with_browser(self, search_url):
        return None

    def retry_failed_journals(self, start_date, end_date, retry_timeout=300):
        logger.info("CELL retry_failed_journals skipped: Crossref-only parser has no failed issue pages")
        return []

    def close_browser(self):
        return None

    def close(self):
        try:
            if self.session:
                self.session.close()
        except Exception as e:
            logger.warning(f"CELL session close failed: {e}")

    def _scrape_crossref_batch(self, journal_name, start_date, end_date):
        issns = self._get_current_issns()
        if not issns:
            logger.info(f"CELL {journal_name}: CSV missing ISSN/EISSN; Crossref skipped")
            return []

        logger.info(
            f"CELL {journal_name}: Crossref only issn={','.join(issns)} "
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
            logger.info(f"CELL {journal_name}: Crossref returned 0 articles")
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
                f"CELL {journal_name}: keyword='{item.get('keyword', '') or 'ALL'}' "
                f"fetched={item.get('fetched', 0)} added={item.get('added', 0)}"
            )
        logger.info(
            f"CELL {journal_name}: Crossref batch candidate={len(rows)}, "
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

    def _doi_from_value(self, value):
        text = str(value or "").strip()
        if not text:
            return ""
        match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I)
        if match:
            return match.group(0).rstrip('.,;)"\'').strip()
        return ""

    def _metadata_result_to_article(self, result, doi, journal_name):
        return {
            "title": result.get("title") or "",
            "url": result.get("url") or f"https://doi.org/{doi}",
            "link": result.get("url") or f"https://doi.org/{doi}",
            "abstract": result.get("abstract") or "",
            "date": result.get("date") or "",
            "doi": result.get("doi") or doi,
            "type": "metadata_repair",
            "journal": result.get("journal") or journal_name,
            "authors": result.get("authors") or "",
            "source": "doi_%s" % (result.get("source") or "metadata"),
        }

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
