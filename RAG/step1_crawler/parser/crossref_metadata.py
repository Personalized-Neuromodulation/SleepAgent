# -*- coding: utf-8 -*-
import logging
import random
import re
import time
from datetime import datetime, timedelta

import requests

from parser.text_cleanup import clean_metadata_text


logger = logging.getLogger(__name__)


class CrossrefMetadataFetcher:
    """Fetch journal-article metadata by ISSN from Crossref."""

    API_URL = "https://api.crossref.org/works"

    def __init__(
        self,
        rows=1000,
        max_pages=None,
        mailto=None,
        min_interval=0.5,
        max_retries=4,
        try_all_issns=False,
        date_chunk_days=365,
    ):
        self.rows = min(1000, max(1, int(rows or 1000)))
        self.max_pages = None if max_pages is None else max(1, int(max_pages))
        self.mailto = mailto
        self.min_interval = max(0.0, float(min_interval or 0))
        self.max_retries = max(1, int(max_retries or 1))
        self.try_all_issns = bool(try_all_issns)
        self.date_chunk_days = None if date_chunk_days is None else max(1, int(date_chunk_days))
        self._last_request_time = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "crawler2025-crossref/1.0 (mailto:%s)" % (mailto or "unknown@example.com"),
        })

    def fetch_by_issn(
        self,
        issns,
        start_date,
        end_date,
        keywords=None,
        journal_name="",
    ):
        """Compatibility collector.

        New code should prefer fetch_by_issn_stream() so Crossref results do
        not accumulate as one large list in memory.
        """
        articles = []

        self.fetch_by_issn_stream(
            issns=issns,
            start_date=start_date,
            end_date=end_date,
            keywords=keywords,
            journal_name=journal_name,
            callback=lambda batch: articles.extend(batch),
            batch_size=max(100, min(self.rows, 1000)),
        )

        return articles

    def fetch_by_issn_stream(
        self,
        issns,
        start_date,
        end_date,
        keywords=None,
        journal_name="",
        callback=None,
        batch_size=200,
    ):
        """Fetch Crossref metadata and emit small batches.

        Memory behavior:
            - Crossref page JSON exists only for the current request.
            - At most `batch_size` mapped article dicts are buffered.
            - A DOI `seen` set is retained for de-duplication.
            - No full-journal article list is built.

        Returns the number of unique emitted records.
        """
        issns = self._normalize_issns(issns)
        if not issns:
            self.last_keyword_stats = []
            return 0

        try:
            batch_size = max(1, int(batch_size or 200))
        except Exception:
            batch_size = 200

        keyword_values = [
            str(k).strip()
            for k in (keywords or [])
            if str(k).strip()
        ]
        if not keyword_values:
            keyword_values = [None]

        seen = set()
        pending = []
        self.last_keyword_stats = []
        date_windows = list(
            self._iter_date_windows(
                start_date,
                end_date,
            )
        )

        def emit(article):
            pending.append(article)

            if len(pending) < batch_size:
                return

            batch = list(pending)
            pending.clear()

            if callback:
                callback(batch)

        for issn_index, issn in enumerate(issns):
            issn_start_count = len(seen)

            for keyword in keyword_values:
                keyword_fetched = 0
                keyword_added = 0
                page_count = 0
                stop_reasons = []

                for window_start, window_end in date_windows:
                    result = self._fetch_window_stream(
                        issn=issn,
                        start_date=window_start,
                        end_date=window_end,
                        keyword=keyword,
                        journal_name=journal_name,
                        seen=seen,
                        emit=emit,
                    )

                    keyword_fetched += result["fetched"]
                    keyword_added += result["added"]
                    page_count += result["pages"]
                    stop_reasons.append(
                        result["stop_reason"]
                    )

                stat = {
                    "issn": issn,
                    "keyword": keyword or "",
                    "fetched": keyword_fetched,
                    "added": keyword_added,
                    "total_added": len(seen),
                    "pages": page_count,
                    "stop_reason": self._summarize_stop_reasons(
                        stop_reasons
                    ),
                    "windows": len(date_windows),
                }

                self.last_keyword_stats.append(stat)

                if keyword_fetched:
                    logger.info(
                        "Crossref %s issn=%s keyword='%s': "
                        "fetched=%s, added=%s, total_added=%s, "
                        "pages=%s, windows=%s, stop=%s",
                        journal_name,
                        issn,
                        keyword or "ALL",
                        keyword_fetched,
                        keyword_added,
                        len(seen),
                        page_count,
                        len(date_windows),
                        stat["stop_reason"],
                    )
                else:
                    logger.info(
                        "Crossref %s issn=%s keyword='%s': no results",
                        journal_name,
                        issn,
                        keyword or "ALL",
                    )

            # Print ISSN and EISSN often resolve to the same Crossref corpus.
            # When configured with try_all_issns=False, stop after the first
            # ISSN that actually emits data.
            if len(seen) > issn_start_count and not self.try_all_issns:
                remaining = len(issns) - issn_index - 1
                if remaining > 0:
                    logger.info(
                        "Crossref %s issn=%s returned results; "
                        "skip %s alternate ISSN/EISSN values",
                        journal_name,
                        issn,
                        remaining,
                    )
                break

        if pending:
            batch = list(pending)
            pending.clear()

            if callback:
                callback(batch)

        return len(seen)

    def _fetch_window_stream(
        self,
        issn,
        start_date,
        end_date,
        keyword,
        journal_name,
        seen,
        emit,
    ):
        cursor = "*"
        fetched = 0
        added = 0
        page_count = 0
        stop_reason = "max_pages"
        previous_page_dois = None
        stale_pages = 0

        while self.max_pages is None or page_count < self.max_pages:
            page_count += 1

            params = {
                "filter": ",".join([
                    "issn:%s" % issn,
                    "from-pub-date:%s" % self._date_text(start_date),
                    "until-pub-date:%s" % self._date_text(end_date),
                    "type:journal-article",
                ]),
                "rows": self.rows,
                "cursor": cursor,
                "sort": "published",
                "order": "asc",
            }

            if keyword:
                params["query"] = keyword

            try:
                message = self._request_message(
                    params,
                    journal_name,
                    issn,
                    keyword,
                )
            except Exception as exc:
                logger.warning(
                    "Crossref fetch failed issn=%s keyword=%s "
                    "journal=%s range=%s..%s: %s",
                    issn,
                    keyword or "",
                    journal_name,
                    self._date_text(start_date),
                    self._date_text(end_date),
                    exc,
                )
                stop_reason = "request_failed"
                break

            items = message.get("items", [])
            fetched += len(items)

            if not items:
                stop_reason = "cursor_exhausted"
                break

            current_page_dois = [
                str(item.get("DOI") or "").strip().lower()
                for item in items
                if str(item.get("DOI") or "").strip()
            ]

            page_added = 0

            for item in items:
                article = self._map_item(item)

                if self._is_non_research_article(
                    article,
                    item,
                ):
                    logger.debug(
                        "Crossref skipped non-research record "
                        "doi=%s title=%s",
                        article.get("doi"),
                        article.get("title"),
                    )
                    continue

                if keyword:
                    article["matched_keyword"] = keyword

                doi_key = str(
                    article.get("doi") or ""
                ).strip().lower()

                if not doi_key or doi_key in seen:
                    continue

                seen.add(doi_key)
                emit(article)
                added += 1
                page_added += 1

            if (
                current_page_dois
                and current_page_dois == previous_page_dois
            ):
                stop_reason = "page_repeated"
                break

            previous_page_dois = current_page_dois

            if page_added == 0:
                stale_pages += 1

                if stale_pages >= 2:
                    stop_reason = "no_new_items"
                    break
            else:
                stale_pages = 0

            if len(items) < self.rows:
                stop_reason = "cursor_exhausted"
                break

            next_cursor = message.get("next-cursor")

            if not next_cursor:
                stop_reason = "cursor_exhausted"
                break

            cursor = next_cursor

        return {
            "fetched": fetched,
            "added": added,
            "pages": page_count,
            "stop_reason": stop_reason,
        }

    def _request_message(self, params, journal_name, issn, keyword):
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            response = self.session.get(self.API_URL, params=params, timeout=30)
            status_code = getattr(response, "status_code", None)

            if status_code == 429:
                last_error = requests.HTTPError(f"429 Too Many Requests for {response.url}", response=response)
                if attempt >= self.max_retries:
                    break
                delay = self._retry_delay(response, attempt)
                logger.warning(
                    "Crossref rate limited issn=%s keyword=%s journal=%s; retry %s/%s after %.1fs",
                    issn,
                    keyword or "",
                    journal_name,
                    attempt,
                    self.max_retries,
                    delay,
                )
                time.sleep(delay)
                continue

            try:
                response.raise_for_status()
                return response.json().get("message", {})
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries or status_code not in (500, 502, 503, 504):
                    break
                delay = self._retry_delay(response, attempt)
                logger.warning(
                    "Crossref transient HTTP %s issn=%s keyword=%s journal=%s; retry %s/%s after %.1fs",
                    status_code,
                    issn,
                    keyword or "",
                    journal_name,
                    attempt,
                    self.max_retries,
                    delay,
                )
                time.sleep(delay)
        raise last_error

    def _throttle(self):
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _retry_delay(self, response, attempt):
        retry_after = getattr(response, "headers", {}).get("Retry-After") if response is not None else None
        if retry_after:
            try:
                return min(120.0, max(1.0, float(retry_after)))
            except Exception:
                pass
        return min(120.0, (2 ** attempt) + random.uniform(0.5, 2.0))

    def _normalize_issns(self, issns):
        result = []
        for issn in issns or []:
            value = str(issn or "").strip()
            if value and value not in result:
                result.append(value)
        return result

    def _iter_date_windows(self, start_date, end_date):
        start = self._date_value(start_date)
        end = self._date_value(end_date)
        if not self.date_chunk_days or start > end:
            yield start_date, end_date
            return
        current = start
        while current <= end:
            window_end = min(end, current + timedelta(days=self.date_chunk_days - 1))
            yield current, window_end
            current = window_end + timedelta(days=1)

    def _date_value(self, value):
        if isinstance(value, datetime):
            return value.date()
        if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
            return value
        return datetime.fromisoformat(str(value)).date()

    def _summarize_stop_reasons(self, reasons):
        values = [str(item or "") for item in reasons if item]
        if not values:
            return ""
        unique = sorted(set(values))
        if len(unique) == 1:
            return unique[0]
        return ",".join("%s:%s" % (value, values.count(value)) for value in unique)

    def _date_text(self, value):
        if isinstance(value, datetime):
            value = value.date()
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def _map_item(self, item):
        doi = (item.get("DOI") or "").strip()
        title_values = item.get("title") or []
        container_values = item.get("container-title") or []
        authors = []
        for author in item.get("author") or []:
            name = " ".join(part for part in [author.get("given"), author.get("family")] if part)
            if name:
                authors.append(name)
        return {
            "doi": doi,
            "title": self._clean_text(title_values[0] if title_values else ""),
            "authors": "; ".join(authors),
            "date": self._extract_date(item),
            "journal": str(container_values[0]).strip() if container_values else "",
            "abstract": self._clean_text(item.get("abstract") or ""),
            "url": "https://doi.org/%s" % doi if doi else (item.get("URL") or ""),
            "article_type": item.get("subtype") or item.get("type") or "",
            "source": "crossref",
        }

    def _extract_date(self, item):
        for key in ("published-print", "published-online", "published", "published-other", "issued"):
            parts = (item.get(key) or {}).get("date-parts") or []
            if not parts or not parts[0]:
                continue
            values = list(parts[0]) + [1, 1]
            try:
                return datetime(int(values[0]), int(values[1]), int(values[2])).date()
            except Exception:
                continue
        return None

    def _is_non_research_article(self, article, raw_item):
        title = (article.get("title") or "").strip().lower()
        article_type = (article.get("article_type") or "").strip().lower()
        raw_subtype = str(raw_item.get("subtype") or raw_item.get("type") or "").strip().lower()
        combined_type = " ".join([article_type, raw_subtype])

        excluded_types = (
            "book-review",
            "book review",
            "book_review",
            "correction",
            "erratum",
            "retraction",
            "news",
            "editorial",
            "letter",
        )
        if any(value in combined_type for value in excluded_types):
            return True

        title_patterns = (
            r"^new books\b",
            r"\bbooks for young scientists\b",
            r"\bbook review\b",
            r"\breviewed by\b",
            r"^this week in science\b",
            r"^editorial\b",
            r"^correction\b",
            r"^erratum\b",
        )
        if any(re.search(pattern, title) for pattern in title_patterns):
            return True

        raw_title = " ".join(str(value or "") for value in (raw_item.get("title") or []))
        bold_count = len(re.findall(r"<\s*b\b", raw_title, flags=re.I))
        if bold_count >= 3 and len(title) > 250:
            return True

        return False

    def _clean_abstract(self, abstract):
        return self._clean_text(abstract)

    def _clean_text(self, value):
        text = clean_metadata_text(value)
        if not text:
            return ""
        return text
