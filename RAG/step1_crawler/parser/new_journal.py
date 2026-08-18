# -*- coding: utf-8 -*-
import logging
import re
from datetime import datetime

from .base import BaseParser
from .crossref_metadata import CrossrefMetadataFetcher


logger = logging.getLogger(__name__)


class NewJournalParser(BaseParser):
    """OTHER journal parser based on Crossref metadata + DOI abstract APIs.

    IMPORTANT:
    - Publisher detail pages are NOT used for abstract repair.
    - Missing abstracts use BaseParser's shared DoiAbstractFetcher:
      Crossref DOI API -> Europe PMC -> OpenAlex -> Semantic Scholar.
    - This parser is used only for the "other" platform.
    """

    def __init__(self, paper_agent=None):
        super().__init__("other", paper_agent)
        self.current_journal_info = {}

        # OTHER metadata path: ISSN -> Crossref.
        # Once one ISSN returns records, alternate ISSN/EISSN values are skipped
        # to avoid downloading the same journal corpus twice.
        self.metadata_fetcher = CrossrefMetadataFetcher(
            try_all_issns=False,
        )

    def set_current_journal_info(self, journal_info):
        self.current_journal_info = journal_info or {}

    def should_use_topic_search(self):
        return True

    def scrape_journal(self, journal_name, base_url, start_date, end_date):
        return self.scrape_journal_topic_search(journal_name, base_url, start_date, end_date)

    def scrape_journal_topic_search(self, journal_name, base_url, start_date, end_date):
        articles = []
        self.scrape_journal_topic_search_stream(
            journal_name=journal_name,
            base_url=base_url,
            start_date=start_date,
            end_date=end_date,
            callback=lambda batch: articles.extend(batch),
        )
        return articles

    def scrape_journal_topic_search_stream(
        self,
        journal_name,
        base_url,
        start_date,
        end_date,
        callback,
    ):
        """Stream Crossref metadata without building a full-journal list."""
        issns = self._get_current_issns()

        if not issns:
            logger.info(
                f"OTHER {journal_name}: CSV未提供ISSN/EISSN，Crossref跳过"
            )
            return super().scrape_journal_topic_search_stream(
                journal_name=journal_name,
                base_url=base_url,
                start_date=start_date,
                end_date=end_date,
                callback=callback,
            )

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
            f"OTHER {journal_name}: Crossref streaming "
            f"issn={','.join(issns)} batch_size={stream_batch_size} "
            f"range={start_date}..{end_date}"
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

        if emitted:
            logger.info(
                f"OTHER {journal_name}: Crossref stream complete "
                f"unique={total_crossref}, metadata_emitted={emitted}, "
                f"date_filtered={date_filtered}"
            )
            return emitted

        logger.info(
            f"OTHER {journal_name}: Crossref returned no usable metadata; "
            f"falling back to topic search"
        )

        return super().scrape_journal_topic_search_stream(
            journal_name=journal_name,
            base_url=base_url,
            start_date=start_date,
            end_date=end_date,
            callback=callback,
        )


    def get_search_page_with_browser(self, search_url):
        return super().get_search_page_with_browser(search_url)

    def _scrape_crossref_batch(self, journal_name, start_date, end_date):
        issns = self._get_current_issns()
        if not issns:
            logger.info(f"OTHER {journal_name}: CSV未提供ISSN/EISSN，Crossref跳过")
            return []

        logger.info(
            f"OTHER {journal_name}: Crossref only issn={','.join(issns)} "
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
            logger.info(f"OTHER {journal_name}: Crossref returned 0 articles")
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

        logger.info(
            f"OTHER {journal_name}: Crossref batch candidate={len(rows)}, "
            f"deduped={len(deduped)}, date_filtered={date_filtered}, "
            f"metadata_kept={len(date_kept)}"
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

