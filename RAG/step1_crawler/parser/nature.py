# -*- coding: utf-8 -*-
"""
Nature journal parser.

Current architecture
--------------------
1. Read ISSN / EISSN from the journal CSV metadata supplied by main.py.
2. Fetch journal-article metadata from Crossref for the requested date range.
3. De-duplicate by DOI and normalize fields.
4. Return/callback metadata to main.py.
5. Missing abstracts are NOT scraped from nature.com here.
   They are repaired centrally by BaseParser.repair_abstract_by_doi(),
   which uses parser/doi_abstract.py:
       Crossref DOI API -> Europe PMC -> OpenAlex -> Semantic Scholar.
6. TOPIC_KEYWORDS filtering, LLM review, and result export are handled by main.py.

Nature archive/search/article-page crawling and the old duplicated LLM workflow
have intentionally been removed from this parser.
"""

import logging
import re

from .base import BaseParser
from .crossref_metadata import CrossrefMetadataFetcher


logger = logging.getLogger(__name__)


class NatureParser(BaseParser):
    """Nature parser using Crossref metadata + shared DOI abstract repair."""

    def __init__(self, paper_agent=None):
        super().__init__("nature", paper_agent)

        self.current_journal_info = {}
        self.issue_result_handler = None

        # Metadata acquisition only.
        # Abstract repair is inherited from BaseParser and uses doi_abstract.py.
        self.metadata_fetcher = CrossrefMetadataFetcher(try_all_issns=False)

    # ------------------------------------------------------------------
    # Interface used by main.py
    # ------------------------------------------------------------------

    def set_current_journal_info(self, journal_info):
        """Receive the current journal row/configuration from main.py."""
        self.current_journal_info = journal_info or {}

    def set_issue_result_handler(self, handler):
        """Compatibility callback used by non-stream callers."""
        self.issue_result_handler = handler

    def should_use_topic_search(self):
        """
        Keep compatibility with the crawler's topic-search interface.

        Despite the method name, Nature no longer searches nature.com.
        scrape_journal_topic_search* delegates to the Crossref metadata flow.
        """
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
                "Nature %s: CSV missing ISSN/EISSN; Crossref skipped",
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
            "Nature %s: Crossref streaming "
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
                "Nature %s: Crossref issn=%s keyword='%s' "
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
            "Nature %s: Crossref stream complete "
            "unique=%s metadata_emitted=%s date_filtered=%s",
            journal_name,
            total_crossref,
            emitted,
            date_filtered,
        )

        return emitted


    def scrape_journal_topic_search(
        self,
        journal_name,
        base_url,
        start_date,
        end_date,
    ):
        """
        Compatibility alias.

        No Nature web search is performed. The method delegates to Crossref.
        """
        return self.scrape_journal(
            journal_name,
            base_url,
            start_date,
            end_date,
        )

    def scrape_journal_topic_search_stream(
        self,
        journal_name,
        base_url,
        start_date,
        end_date,
        callback=None,
    ):
        """
        Compatibility alias used by the Nature branch in main.py.

        No Nature search page is visited.
        """
        return self.scrape_journal_stream(
            journal_name,
            base_url,
            start_date,
            end_date,
            callback=callback,
        )

    # ------------------------------------------------------------------
    # Crossref metadata acquisition
    # ------------------------------------------------------------------

    def _scrape_crossref_batch(
        self,
        journal_name,
        start_date,
        end_date,
    ):
        """
        Fetch all Crossref journal-article metadata for the current Nature title.

        Crossref query dimensions:
            ISSN / EISSN
            + publication date range
            + type=journal-article

        No topic keyword is sent to Crossref (`keywords=None`).
        Topic filtering is performed later by main.py.
        """
        issns = self._get_current_issns()

        if not issns:
            logger.info(
                "Nature %s: CSV missing ISSN/EISSN; Crossref skipped",
                journal_name,
            )
            return []

        logger.info(
            "Nature %s: Crossref only issn=%s keywords=disabled range=%s..%s",
            journal_name,
            ",".join(issns),
            start_date,
            end_date,
        )

        rows = self.metadata_fetcher.fetch_by_issn(
            issns=issns,
            start_date=start_date,
            end_date=end_date,
            keywords=None,
            journal_name=journal_name,
        )

        if not rows:
            logger.info(
                "Nature %s: Crossref returned 0 articles",
                journal_name,
            )
            return []

        deduped = self._dedupe_metadata_by_doi(rows)

        date_kept = []
        date_filtered = 0

        for row in deduped:
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
            article["quality_score"] = self.validate_article(article)
            date_kept.append(article)

        for stat in self._iter_keyword_stats():
            logger.info(
                "Nature %s: Crossref issn=%s keyword='%s' "
                "fetched=%s added=%s pages=%s windows=%s stop=%s",
                journal_name,
                stat.get("issn", ""),
                stat.get("keyword", "") or "ALL",
                stat.get("fetched", 0),
                stat.get("added", 0),
                stat.get("pages", 0),
                stat.get("windows", 0),
                stat.get("stop_reason", ""),
            )

        logger.info(
            "Nature %s: Crossref batch candidate=%s, "
            "deduped=%s, date_filtered=%s, metadata_kept=%s",
            journal_name,
            len(rows),
            len(deduped),
            date_filtered,
            len(date_kept),
        )

        return date_kept

    # ------------------------------------------------------------------
    # Journal metadata helpers
    # ------------------------------------------------------------------

    def _get_current_issns(self):
        """
        Extract ISSN/EISSN values from the current CSV journal record.

        Accepted key forms include:
            ISSN
            EISSN
            print_issn
            online_issn
        """
        source_row = {}

        if isinstance(self.current_journal_info, dict):
            source_row = (
                self.current_journal_info.get("source_row")
                or {}
            )

        values = []

        for container in (
            self.current_journal_info or {},
            source_row,
        ):
            for key, value in (container or {}).items():
                normalized_key = (
                    str(key or "")
                    .strip()
                    .lower()
                    .replace("-", "")
                    .replace("_", "")
                )

                if normalized_key in (
                    "issn",
                    "eissn",
                    "printissn",
                    "onlineissn",
                ):
                    values.append(value)

        issns = []

        for value in values:
            for part in re.split(
                r"[;,/|\s]+",
                str(value or ""),
            ):
                compact = (
                    part.strip()
                    .upper()
                    .replace("-", "")
                )

                if not re.fullmatch(
                    r"\d{7}[\dX]",
                    compact,
                ):
                    continue

                formatted = (
                    f"{compact[:4]}-{compact[4:]}"
                )

                if formatted not in issns:
                    issns.append(formatted)

        return issns

    def _iter_keyword_stats(self):
        """
        Yield Crossref fetch statistics.

        The name is retained for compatibility with CrossrefMetadataFetcher,
        even though Nature currently requests keyword='ALL'.
        """
        stats = getattr(
            self.metadata_fetcher,
            "last_keyword_stats",
            [],
        )

        if isinstance(stats, dict):
            for keyword, item in stats.items():
                row = dict(item or {})
                row.setdefault(
                    "keyword",
                    keyword,
                )
                yield row
            return

        if isinstance(stats, list):
            for item in stats:
                if isinstance(item, dict):
                    yield item

    @staticmethod
    def _dedupe_metadata_by_doi(rows):
        """
        De-duplicate Crossref records by DOI.

        Records without DOI are skipped because the downstream shared abstract
        repair and crawler checkpoint logic use DOI as the primary identifier.
        """
        seen = set()
        deduped = []

        for row in rows or []:
            doi = str(
                row.get("doi") or ""
            ).strip()

            doi_key = doi.lower()

            if not doi_key:
                continue

            if doi_key in seen:
                continue

            seen.add(doi_key)
            deduped.append(row)

        return deduped

    @staticmethod
    def _normalize_article(row, journal_name):
        """Normalize a Crossref row to the common crawler article schema."""
        article = dict(row or {})

        doi = str(
            article.get("doi") or ""
        ).strip()

        if doi:
            article["doi"] = doi

            if not str(
                article.get("url") or ""
            ).strip():
                article["url"] = (
                    f"https://doi.org/{doi}"
                )

        article.setdefault(
            "journal",
            journal_name,
        )
        article.setdefault(
            "title",
            "",
        )
        article.setdefault(
            "abstract",
            "",
        )
        article.setdefault(
            "authors",
            "",
        )
        article.setdefault(
            "article_type",
            article.get("type", ""),
        )

        article["source"] = (
            article.get("source")
            or "crossref"
        )

        return article

    @staticmethod
    def validate_article(article):
        """
        Lightweight metadata completeness score.

        title     20
        DOI       30
        abstract  30
        date      20
        total    100
        """
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

    # ------------------------------------------------------------------
    # Explicitly disabled publisher-page search/detail APIs
    # ------------------------------------------------------------------

    def build_topic_search_url(
        self,
        journal_name,
        base_url,
        keyword,
        page=1,
    ):
        """
        Nature publisher-page topic search is disabled.

        Returning None prevents accidental reactivation of the legacy
        nature.com search crawler.
        """
        return None

    def extract_candidate_urls_from_search_page(
        self,
        html,
        base_url,
    ):
        """Nature publisher search parsing is disabled."""
        return []

    def fetch_article_details_for_topic_search(
        self,
        url,
        journal_name,
    ):
        """
        Publisher article-page detail scraping is disabled for normal repair.

        Missing abstracts must go through:
            BaseParser.repair_abstract_by_doi()
            -> parser/doi_abstract.py
        """
        return None
