import unittest
from datetime import date

from parser.crossref_metadata import CrossrefMetadataFetcher
from parser.new_journal import NewJournalParser


class OtherMetadataFirstTests(unittest.TestCase):
    def test_other_stream_uses_crossref_only(self):
        parser = NewJournalParser()
        parser.set_current_journal_info({
            "name": "Example Journal",
            "link": "https://example.org/journal",
            "source_row": {"ISSN": "1234-5678", "EISSN": ""},
        })
        calls = []
        parser.metadata_fetcher.fetch_by_issn = lambda **kwargs: calls.append(("crossref", kwargs)) or [{
            "title": "Sleep paper",
            "abstract": "Sleep physiology",
            "doi": "10.1000/sleep",
            "date": date(2026, 1, 2),
            "url": "https://example.org/doi/10.1000/sleep",
            "authors": "Ada Lovelace",
            "journal": "Example Journal",
        }]
        parser.get_search_html_with_fallback = lambda *args, **kwargs: self.fail("publisher search should not run")

        batches = []
        articles = parser.scrape_journal_topic_search_stream(
            "Example Journal",
            "https://example.org/journal",
            date(2026, 1, 1),
            date(2026, 1, 31),
            callback=lambda batch: batches.append(batch),
        )

        self.assertEqual(calls[0][0], "crossref")
        self.assertEqual(calls[0][1]["keywords"], None)
        self.assertEqual(articles[0]["doi"], "10.1000/sleep")
        self.assertEqual(batches[0][0]["quality_score"], 100)

    def test_other_stream_callbacks_once_with_journal_batch(self):
        parser = NewJournalParser()
        parser.set_current_journal_info({
            "name": "Example Journal",
            "link": "https://example.org/journal",
            "source_row": {"ISSN": "1234-5678"},
        })
        parser.metadata_fetcher.fetch_by_issn = lambda **kwargs: [
            {
                "title": "Sleep paper one",
                "abstract": "Sleep physiology",
                "doi": "10.1000/one",
                "date": date(2026, 1, 2),
                "url": "https://example.org/doi/10.1000/one",
            },
            {
                "title": "Sleep paper two",
                "abstract": "REM sleep",
                "doi": "10.1000/two",
                "date": date(2026, 1, 3),
                "url": "https://example.org/doi/10.1000/two",
            },
        ]
        batches = []
        articles = parser.scrape_journal_topic_search_stream(
            "Example Journal",
            "https://example.org/journal",
            date(2026, 1, 1),
            date(2026, 1, 31),
            callback=lambda batch: batches.append(batch),
        )

        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 2)
        self.assertEqual([a["doi"] for a in articles], ["10.1000/one", "10.1000/two"])

    def test_other_stream_returns_empty_when_crossref_empty(self):
        parser = NewJournalParser()
        parser.set_current_journal_info({
            "name": "Example Journal",
            "link": "https://example.org/journal",
            "source_row": {"ISSN": "1234-5678"},
        })
        parser.metadata_fetcher.fetch_by_issn = lambda **kwargs: []
        parser.get_search_html_with_fallback = lambda *args, **kwargs: self.fail("publisher search should not run")

        articles = parser.scrape_journal_topic_search(
            "Example Journal",
            "https://example.org/journal",
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

        self.assertEqual(articles, [])

    def test_other_disables_publisher_search_interface(self):
        parser = NewJournalParser()

        self.assertIsNone(parser.build_topic_search_url("Example", "https://example.org", "sleep", 1))
        self.assertEqual(parser.extract_candidate_urls_from_search_page("<html></html>", "https://example.org"), [])
        self.assertIsNone(parser.get_search_page_with_browser("https://example.org/search?q=sleep"))

    def test_crossref_fetcher_omits_query_when_keywords_are_none(self):
        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "message": {
                        "items": [{
                            "DOI": "10.1000/sleep",
                            "title": ["Sleep paper"],
                            "container-title": ["Example Journal"],
                            "issued": {"date-parts": [[2026, 1, 2]]},
                        }],
                        "next-cursor": None,
                    }
                }

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.params = []

            def get(self, url, params=None, timeout=30):
                self.params.append(dict(params or {}))
                return FakeResponse()

        fetcher = CrossrefMetadataFetcher(rows=10, max_pages=1, min_interval=0)
        fake_session = FakeSession()
        fetcher.session = fake_session

        articles = fetcher.fetch_by_issn(
            issns=["1234-5678"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            keywords=None,
            journal_name="Example Journal",
        )

        self.assertTrue(all("select" not in p for p in fake_session.params))
        self.assertTrue(all("query" not in p for p in fake_session.params))
        self.assertEqual(len(articles), 1)
        self.assertNotIn("matched_keyword", articles[0])
        self.assertEqual(fetcher.last_keyword_stats[0]["fetched"], 1)
        self.assertEqual(fetcher.last_keyword_stats[0]["added"], 1)
        self.assertEqual(fetcher.last_keyword_stats[0]["total_added"], 1)

    def test_crossref_clean_text_restores_symbol_replacements(self):
        fetcher = CrossrefMetadataFetcher(rows=10, max_pages=1, min_interval=0)
        self.assertEqual(
            fetcher._clean_text("HIF-1�� and BMAL1 in bone regeneration"),
            "HIF-1α and BMAL1 in bone regeneration",
        )
        self.assertEqual(
            fetcher._clean_text("REG�� regulates circadian clock"),
            "REGγ regulates circadian clock",
        )

    def test_crossref_fetcher_default_pages_until_cursor_exhausted(self):
        class FakeResponse:
            status_code = 200

            def __init__(self, doi, next_cursor):
                self.doi = doi
                self.next_cursor = next_cursor

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "message": {
                        "items": [{
                            "DOI": self.doi,
                            "title": [f"Paper {self.doi}"],
                            "container-title": ["Example Journal"],
                            "issued": {"date-parts": [[2026, 1, 2]]},
                        }],
                        "next-cursor": self.next_cursor,
                    }
                }

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.calls = 0

            def get(self, url, params=None, timeout=30):
                self.calls += 1
                if self.calls == 1:
                    return FakeResponse("10.1000/one", "cursor-2")
                if self.calls == 2:
                    return FakeResponse("10.1000/two", "cursor-3")
                return FakeResponse("10.1000/three", None)

        fetcher = CrossrefMetadataFetcher(rows=1, min_interval=0)
        fake_session = FakeSession()
        fetcher.session = fake_session

        articles = fetcher.fetch_by_issn(
            issns=["1234-5678"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            keywords=None,
            journal_name="Example Journal",
        )

        self.assertEqual(fake_session.calls, 3)
        self.assertEqual([article["doi"] for article in articles], ["10.1000/one", "10.1000/two", "10.1000/three"])

    def test_crossref_fetcher_continues_when_same_cursor_has_new_items(self):
        class FakeResponse:
            status_code = 200

            def __init__(self, doi, next_cursor="*"):
                self.doi = doi
                self.next_cursor = next_cursor

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "message": {
                        "items": [{
                            "DOI": self.doi,
                            "title": [f"Paper {self.doi}"],
                            "container-title": ["Example Journal"],
                            "issued": {"date-parts": [[2026, 1, 2]]},
                        }],
                        "next-cursor": self.next_cursor,
                    }
                }

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.calls = 0

            def get(self, url, params=None, timeout=30):
                self.calls += 1
                if self.calls == 1:
                    return FakeResponse("10.1000/one")
                if self.calls == 2:
                    return FakeResponse("10.1000/two")
                return FakeResponse("10.1000/two")

        fetcher = CrossrefMetadataFetcher(rows=1, min_interval=0, date_chunk_days=None)
        fake_session = FakeSession()
        fetcher.session = fake_session

        articles = fetcher.fetch_by_issn(
            issns=["1234-5678"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            keywords=None,
            journal_name="Example Journal",
        )

        self.assertEqual([article["doi"] for article in articles], ["10.1000/one", "10.1000/two"])
        self.assertEqual(fake_session.calls, 3)
        self.assertEqual(fetcher.last_keyword_stats[0]["stop_reason"], "page_repeated")

    def test_crossref_fetcher_chunks_date_range(self):
        class FakeResponse:
            status_code = 200

            def __init__(self, doi):
                self.doi = doi

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "message": {
                        "items": [{
                            "DOI": self.doi,
                            "title": [f"Paper {self.doi}"],
                            "container-title": ["Example Journal"],
                            "issued": {"date-parts": [[2026, 1, 2]]},
                        }],
                    }
                }

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.filters = []

            def get(self, url, params=None, timeout=30):
                filter_value = dict(params or {})["filter"]
                self.filters.append(filter_value)
                if "until-pub-date:2026-01-31" in filter_value:
                    return FakeResponse("10.1000/january")
                return FakeResponse("10.1000/february")

        fetcher = CrossrefMetadataFetcher(min_interval=0, date_chunk_days=31)
        fake_session = FakeSession()
        fetcher.session = fake_session

        articles = fetcher.fetch_by_issn(
            issns=["1234-5678"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 2, 15),
            keywords=None,
            journal_name="Example Journal",
        )

        self.assertEqual([article["doi"] for article in articles], ["10.1000/january", "10.1000/february"])
        self.assertIn("from-pub-date:2026-01-01", fake_session.filters[0])
        self.assertIn("until-pub-date:2026-01-31", fake_session.filters[0])
        self.assertIn("from-pub-date:2026-02-01", fake_session.filters[1])
        self.assertIn("until-pub-date:2026-02-15", fake_session.filters[1])

    def test_crossref_fetcher_treats_short_page_as_exhausted_even_with_repeated_cursor(self):
        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "message": {
                        "items": [{
                            "DOI": "10.1000/final",
                            "title": ["Final page"],
                            "container-title": ["Example Journal"],
                            "issued": {"date-parts": [[2026, 1, 2]]},
                        }],
                        "next-cursor": "*",
                    }
                }

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.calls = 0

            def get(self, url, params=None, timeout=30):
                self.calls += 1
                return FakeResponse()

        fetcher = CrossrefMetadataFetcher(rows=10, min_interval=0, date_chunk_days=None)
        fake_session = FakeSession()
        fetcher.session = fake_session

        articles = fetcher.fetch_by_issn(
            issns=["1234-5678"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            keywords=None,
            journal_name="Example Journal",
        )

        self.assertEqual(fake_session.calls, 1)
        self.assertEqual([article["doi"] for article in articles], ["10.1000/final"])
        self.assertEqual(fetcher.last_keyword_stats[0]["stop_reason"], "cursor_exhausted")

    def test_crossref_fetcher_retries_429_with_retry_after(self):
        class FakeResponse:
            def __init__(self, status_code, payload=None, headers=None):
                self.status_code = status_code
                self._payload = payload or {}
                self.headers = headers or {}
                self.url = "https://api.crossref.org/works"

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise Exception(f"HTTP {self.status_code}")

            def json(self):
                return self._payload

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.calls = 0

            def get(self, url, params=None, timeout=30):
                self.calls += 1
                if self.calls == 1:
                    return FakeResponse(429, headers={"Retry-After": "2"})
                return FakeResponse(200, {
                    "message": {
                        "items": [{
                            "DOI": "10.1000/retry",
                            "title": ["Retry paper"],
                            "container-title": ["Example Journal"],
                            "issued": {"date-parts": [[2026, 1, 2]]},
                        }],
                        "next-cursor": None,
                    }
                })

        fetcher = CrossrefMetadataFetcher(rows=10, max_pages=1, min_interval=0, max_retries=2)
        fake_session = FakeSession()
        fetcher.session = fake_session

        import parser.crossref_metadata as crossref_module
        original_sleep = crossref_module.time.sleep
        sleeps = []
        crossref_module.time.sleep = lambda seconds: sleeps.append(seconds)
        try:
            articles = fetcher.fetch_by_issn(
                issns=["1234-5678"],
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                keywords=["sleep"],
                journal_name="Example Journal",
            )
        finally:
            crossref_module.time.sleep = original_sleep

        self.assertEqual(fake_session.calls, 2)
        self.assertEqual(sleeps, [2.0])
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["doi"], "10.1000/retry")

    def test_crossref_fetcher_queries_all_issns_by_default_and_dedupes_doi(self):
        class FakeResponse:
            def __init__(self, doi):
                self.status_code = 200
                self.doi = doi

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "message": {
                        "items": [{
                            "DOI": self.doi,
                            "title": ["ISSN paper"],
                            "container-title": ["Example Journal"],
                            "issued": {"date-parts": [[2026, 1, 2]]},
                        }],
                        "next-cursor": None,
                    }
                }

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.params = []

            def get(self, url, params=None, timeout=30):
                self.params.append(dict(params or {}))
                if len(self.params) == 1:
                    return FakeResponse("10.1000/shared")
                return FakeResponse("10.1000/secondary")

        fetcher = CrossrefMetadataFetcher(rows=10, max_pages=1, min_interval=0)
        fake_session = FakeSession()
        fetcher.session = fake_session

        articles = fetcher.fetch_by_issn(
            issns=["1234-5678", "8765-4321"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            keywords=["sleep"],
            journal_name="Example Journal",
        )

        self.assertEqual(len(fake_session.params), 2)
        self.assertIn("issn:1234-5678", fake_session.params[0]["filter"])
        self.assertIn("issn:8765-4321", fake_session.params[1]["filter"])
        self.assertEqual([article["doi"] for article in articles], ["10.1000/shared", "10.1000/secondary"])

    def test_crossref_fetcher_can_skip_alternate_issn_when_requested(self):
        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "message": {
                        "items": [{
                            "DOI": "10.1000/primary",
                            "title": ["Primary ISSN paper"],
                            "container-title": ["Example Journal"],
                            "issued": {"date-parts": [[2026, 1, 2]]},
                        }],
                        "next-cursor": None,
                    }
                }

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.params = []

            def get(self, url, params=None, timeout=30):
                self.params.append(dict(params or {}))
                return FakeResponse()

        fetcher = CrossrefMetadataFetcher(rows=10, max_pages=1, min_interval=0, try_all_issns=False)
        fake_session = FakeSession()
        fetcher.session = fake_session

        articles = fetcher.fetch_by_issn(
            issns=["1234-5678", "8765-4321"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            keywords=["sleep"],
            journal_name="Example Journal",
        )

        self.assertEqual(len(fake_session.params), 1)
        self.assertEqual(articles[0]["doi"], "10.1000/primary")

    def test_crossref_fetcher_defaults_to_largest_crossref_page_size(self):
        fetcher = CrossrefMetadataFetcher(min_interval=0)

        self.assertEqual(fetcher.rows, 1000)

    def test_crossref_fetcher_skips_book_list_records_with_html_title(self):
        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "message": {
                        "items": [{
                            "DOI": "10.1126/science.booklist",
                            "title": [
                                "New books for young scientists "
                                "<b>Fox: A Circle of Life Story</b>, "
                                "<b>Snoozefest: The Surprising Science of Sleep</b>, "
                                "<b>The Last Days of the Dinosaurs</b>"
                            ],
                            "container-title": ["Science"],
                            "issued": {"date-parts": [[2022, 6, 1]]},
                            "subtype": "book-review",
                        }],
                        "next-cursor": None,
                    }
                }

        class FakeSession:
            def __init__(self):
                self.headers = {}

            def get(self, url, params=None, timeout=30):
                return FakeResponse()

        fetcher = CrossrefMetadataFetcher(rows=10, max_pages=1, min_interval=0)
        fetcher.session = FakeSession()

        articles = fetcher.fetch_by_issn(
            issns=["0036-8075"],
            start_date=date(2022, 1, 1),
            end_date=date(2022, 12, 31),
            keywords=["sleep"],
            journal_name="Science",
        )

        self.assertEqual(articles, [])


if __name__ == "__main__":
    unittest.main()
