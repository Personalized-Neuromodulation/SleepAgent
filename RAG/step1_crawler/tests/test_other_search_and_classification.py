import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from parser.new_journal import NewJournalParser
from parser.science import ScienceParser
from parser.cell import CellParser
from crawler_light.parser.nature import NatureParser
from parser.plos import PLOSParser
from parser.factory import create_parser
from parser.base import BaseParser
from tools.topic_utils import TopicConfig, article_matches_topic, is_challenge_page, load_supported_journals_from_csv


class OtherSearchAndClassificationTests(unittest.TestCase):
    def test_science_search_extraction_is_disabled(self):
        parser = ScienceParser()
        html = """
        <html><body>
          <a href="/doi/10.1126/science.test">Paper</a>
        </body></html>
        """

        urls = parser.extract_candidate_urls_from_search_page(html, "https://www.science.org")

        self.assertEqual(urls, [])

    def test_science_crossref_batch_uses_issue_callback(self):
        class Agent:
            topic_name = "sleep"
            topic_keywords = ["sleep"]
            config = {"TOPIC_SEARCH_MAX_PAGES_PER_KEYWORD": 1}

        parser = ScienceParser(Agent())
        parser.set_current_journal_info({
            "name": "Science",
            "link": "https://www.science.org/journal/science",
            "source_row": {"ISSN": "0036-8075", "EISSN": "1095-9203"},
        })
        parser.metadata_fetcher.fetch_by_issn = lambda **kwargs: [{
            "title": "Sleep regulation in neural circuits",
            "abstract": "Sleep restores brain function.",
            "doi": "10.1126/science.test",
            "url": "https://doi.org/10.1126/science.test",
            "date": date(2026, 1, 15),
            "journal": "Science",
            "authors": "Ada Lovelace",
        }]
        batches = []
        parser.set_issue_result_handler(lambda batch, title: batches.append((title, batch)))

        result = parser.scrape_journal(
            "Science",
            "https://www.science.org/journal/science",
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

        self.assertEqual(result, [])
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0][0], "Crossref metadata")
        self.assertEqual(batches[0][1][0]["doi"], "10.1126/science.test")

    def test_other_uses_generic_search_without_platform_cascade(self):
        parser = NewJournalParser()
        parser._other_strategy_factories = [("nature", "topic", lambda paper_agent: self.fail("cascade should not run"))]
        parser.get_topic_search_keywords = lambda: ["sleep"]
        parser.get_topic_search_max_pages = lambda: 1
        parser.get_search_html_with_fallback = lambda url, timeout=15: "<html></html>"

        articles = parser.scrape_journal_topic_search(
            "Example Journal",
            "https://www.nejm.org/",
            date(2020, 1, 1),
            date(2026, 1, 1),
        )

        self.assertEqual(articles, [])

    def test_other_publisher_search_url_is_disabled(self):
        parser = NewJournalParser()

        url = parser.build_topic_search_url(
            "NEW ENGLAND JOURNAL OF MEDICINE",
            "https://www.nejm.org/",
            "sleep",
            page=1,
        )

        self.assertIsNone(url)

    def test_other_browser_search_is_disabled(self):
        parser = NewJournalParser()

        html = parser.get_search_page_with_browser("https://www.sciencedirect.com/search?qs=sleep")

        self.assertIsNone(html)

    def test_nejm_search_is_disabled(self):
        parser = NewJournalParser()

        url = parser.build_topic_search_url(
            "NEW ENGLAND JOURNAL OF MEDICINE",
            "http://www.nejm.org/",
            "sleep",
            page=1,
        )

        self.assertIsNone(url)

    def test_other_detail_fetch_uses_generic_metadata_parser(self):
        parser = NewJournalParser()

        class Response:
            status_code = 200
            text = """
            <html><head>
              <meta name="citation_title" content="Restless legs syndrome">
              <meta name="citation_abstract" content="A sleep-related movement disorder.">
              <meta name="citation_doi" content="10.1000/restless">
              <meta name="citation_publication_date" content="2026-01-02">
            </head><body></body></html>
            """

            def raise_for_status(self):
                return None

        parser.session.get = lambda url, timeout=30: Response()

        article = parser.fetch_article_details_for_topic_search(
            "https://molecular-cancer.biomedcentral.com/article/10.1186/test",
            "Molecular Cancer",
        )

        self.assertEqual(article["title"], "Restless legs syndrome")
        self.assertEqual(article["abstract"], "A sleep-related movement disorder.")
        self.assertEqual(article["doi"], "10.1000/restless")

    def test_other_detail_page_parsing_is_removed(self):
        parser = NewJournalParser()
        self.assertFalse(hasattr(parser, "_fetch_detail"))

    def test_other_detail_returns_none_when_page_has_no_title(self):
        parser = NewJournalParser()
        parser.session.get = lambda url, timeout=30: type(
            "Response",
            (),
            {
                "status_code": 200,
                "text": "<html><body>No article metadata</body></html>",
                "raise_for_status": lambda self: None,
            },
        )()

        self.assertIsNone(parser.fetch_article_details_for_topic_search("https://example.org/article", "Example"))

    def test_topic_search_logs_date_filter_reason_and_range(self):
        parser = BaseParser("other")
        parser.get_topic_search_keywords = lambda: ["sleep"]
        parser.get_topic_search_max_pages = lambda: 1
        parser.get_search_html_with_fallback = lambda url, timeout=15: "<html></html>"
        parser.extract_candidate_urls_from_search_page = lambda html, base_url: ["https://example.org/article"]
        parser.fetch_article_details_for_topic_search = lambda url, journal_name: {
            "title": "Future sleep paper",
            "abstract": "sleep",
            "url": url,
            "date": date(2026, 8, 1),
            "doi": "10.1000/future",
        }

        with self.assertLogs("parser.base", level="INFO") as logs:
            articles = parser.scrape_journal_topic_search(
                "Example",
                "https://example.org",
                date(2026, 7, 1),
                date(2026, 7, 28),
            )

        self.assertEqual(articles, [])
        text = "\n".join(logs.output)
        self.assertIn("reason=日期超出范围", text)
        self.assertIn("article_date=2026-08-01", text)
        self.assertIn("range=2026-07-01..2026-07-28", text)

    def test_sciencedirect_search_is_disabled(self):
        parser = NewJournalParser()

        url = parser.build_topic_search_url(
            "LANCET",
            "https://www.sciencedirect.com/journal/the-lancet",
            "sleep",
            page=1,
        )

        self.assertIsNone(url)

    def test_sciencedirect_search_https_mapping_is_removed(self):
        parser = NewJournalParser()

        url = parser.build_topic_search_url(
            "CANCER CELL",
            "http://www.sciencedirect.com/journal/cancer-cell",
            "sleep",
            page=1,
        )

        self.assertIsNone(url)

    def test_annualreviews_search_is_disabled(self):
        parser = NewJournalParser()

        url = parser.build_topic_search_url(
            "Annual Review of Psychology",
            "http://www.annualreviews.org/journal/psych",
            "polysomnography",
            page=1,
        )

        self.assertIsNone(url)

    def test_annualreviews_candidate_extraction_is_disabled(self):
        parser = NewJournalParser()
        html = """
        <html><body>
          <a href="/content/journals/10.1146/annurev-psych-020821-113047">Paper</a>
          <a href="/journal/psych">Journal home</a>
        </body></html>
        """

        urls = parser.extract_candidate_urls_from_search_page(
            html,
            "http://www.annualreviews.org/journal/psych",
        )

        self.assertEqual(urls, [])

    def test_candidate_extraction_accepts_www_and_bare_host_variants(self):
        parser = BaseParser("other")
        html = """
        <html><body>
          <a href="https://sciencedirect.com/science/article/pii/S0140673624000012">Paper</a>
        </body></html>
        """

        urls = parser.extract_candidate_urls_from_search_page(
            html,
            "https://www.sciencedirect.com/journal/the-lancet",
        )

        self.assertEqual(
            urls,
            ["https://sciencedirect.com/science/article/pii/S0140673624000012"],
        )

    def test_sciencedirect_cell_names_are_classified_from_url_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "journals.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["期刊名称", "期刊URL"])
                writer.writerow(["CELL", "https://www.sciencedirect.com/journal/cell"])
                writer.writerow(["CANCER CELL", "https://www.sciencedirect.com/journal/cancer-cell"])

            groups, _ = load_supported_journals_from_csv(csv_path)

        self.assertEqual(groups["cell"], [])
        self.assertEqual([item["name"] for item in groups["other"]], ["CELL", "CANCER CELL"])
        self.assertEqual(groups["other"][1]["link"], "https://www.sciencedirect.com/journal/cancer-cell")
        self.assertEqual(groups["other"][1]["csv_link"], "https://www.sciencedirect.com/journal/cancer-cell")

    def test_all_platform_families_keep_csv_url_as_parser_link(self):
        rows = [
            ("Nature Sleep", "https://www.nature.com/journal/example"),
            ("Science Sleep", "https://www.science.org/journal/example"),
            ("Cell Sleep", "https://www.cell.com/cell/home"),
            ("PLOS Sleep", "https://journals.plos.org/plosone"),
            ("Other Sleep", "https://example.org/journal/sleep"),
            ("IEEE Sleep", "http://ieeexplore.ieee.org/servlet/opac?punumber=7333"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "journals.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["journal", "url"])
                writer.writerows(rows)

            groups, _ = load_supported_journals_from_csv(csv_path)

        by_name = {
            item["name"]: item
            for family_items in groups.values()
            for item in family_items
        }
        for name, csv_url in rows:
            self.assertEqual(by_name[name]["link"], csv_url)
            self.assertEqual(by_name[name]["csv_link"], csv_url)

    def test_shared_publisher_url_keeps_distinct_issn_journals(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "journals.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["journal", "ISSN", "EISSN", "url"])
                writer.writerow(["IEEE One", "1111-1111", "", "http://ieeexplore.ieee.org/servlet/opac"])
                writer.writerow(["IEEE Two", "2222-2222", "", "http://ieeexplore.ieee.org/servlet/opac"])
                writer.writerow(["IEEE One Duplicate", "1111-1111", "", "http://ieeexplore.ieee.org/servlet/opac"])

            groups, _ = load_supported_journals_from_csv(csv_path)

        self.assertEqual([item["name"] for item in groups["other"]], ["IEEE One", "IEEE Two"])

    def test_short_topic_keyword_requires_word_boundary(self):
        topic = TopicConfig(name="sleep", keywords=["REM"])

        self.assertFalse(article_matches_topic({"title": "Hints of hope with remdesivir", "abstract": ""}, topic))
        self.assertFalse(article_matches_topic({"title": "Inhibiting peptidoglycan remodelling", "abstract": ""}, topic))
        self.assertTrue(article_matches_topic({"title": "REM sleep changes after treatment", "abstract": ""}, topic))

    def test_cloudflare_powering_internet_page_is_challenge(self):
        html = """
        <html><body>
          <h1>Everything we learned from powering 20% of the Internet—yours by default</h1>
        </body></html>
        """

        self.assertTrue(is_challenge_page(html))

    def test_cell_crossref_batch_uses_issue_callback(self):
        class Agent:
            topic_name = "sleep"
            topic_keywords = ["sleep"]
            config = {"TOPIC_SEARCH_MAX_PAGES_PER_KEYWORD": 1}

        parser = CellParser(Agent())
        parser.set_current_journal_info({
            "name": "CELL",
            "link": "https://www.cell.com/cell/home",
            "source_row": {"ISSN": "0092-8674", "EISSN": ""},
        })
        parser.metadata_fetcher.fetch_by_issn = lambda **kwargs: [{
            "title": "Sleep timing controls cellular repair",
            "abstract": "Sleep restores cellular function.",
            "doi": "10.1016/j.cell.2026.01.001",
            "url": "https://doi.org/10.1016/j.cell.2026.01.001",
            "date": date(2026, 1, 15),
            "journal": "CELL",
            "authors": "Ada Lovelace",
        }]
        batches = []
        parser.set_issue_result_handler(lambda batch, title: batches.append((title, batch)))

        result = parser.scrape_journal(
            "CELL",
            "https://www.cell.com/cell/home",
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

        self.assertEqual(result, [])
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0][0], "Crossref metadata")
        self.assertEqual(batches[0][1][0]["doi"], "10.1016/j.cell.2026.01.001")

    def test_cell_detail_fetch_uses_doi_metadata_not_publisher_page(self):
        parser = CellParser()
        parser.session.get = lambda *args, **kwargs: self.fail("Cell detail repair must not request publisher pages")
        parser.abstract_fetcher.fetch_by_doi = lambda doi: {
            "doi": doi,
            "title": "Sleep Cell paper",
            "abstract": "Cell abstract about sleep.",
            "date": "2026-01-02",
            "source": "europe_pmc",
        }

        article = parser.fetch_article_details_for_topic_search(
            "https://doi.org/10.1016/j.cell.2026.01.001",
            "Cell",
        )

        self.assertEqual(article["title"], "Sleep Cell paper")
        self.assertEqual(article["abstract"], "Cell abstract about sleep.")
        self.assertEqual(article["doi"], "10.1016/j.cell.2026.01.001")
        self.assertEqual(article["source"], "doi_europe_pmc")

    def test_cell_repair_article_from_url_uses_doi_metadata(self):
        parser = CellParser()
        parser.abstract_fetcher.fetch_by_doi = lambda doi: {
            "doi": doi,
            "title": "Sleep Loss Can Cause Death",
            "abstract": "Sleep deprivation leads to mortality.",
            "source": "openalex",
        }

        article = parser.repair_article_from_url({
            "doi": "10.1016/j.cell.2020.02.044",
            "title": "Sleep Loss Can Cause Death",
            "abstract": "",
        }, "Cell")

        self.assertEqual(article["abstract"], "Sleep deprivation leads to mortality.")
        self.assertEqual(article["source"], "doi_openalex")

    def test_nature_crossref_batch_uses_stream_callback_without_keyword_query(self):
        class Agent:
            topic_name = "sleep"
            topic_keywords = ["sleep"]
            config = {"TOPIC_SEARCH_MAX_PAGES_PER_KEYWORD": 1}

        parser = NatureParser(Agent())
        parser.set_current_journal_info({
            "name": "Nature",
            "link": "https://www.nature.com/nature",
            "source_row": {"ISSN": "0028-0836"},
        })
        calls = []
        parser.metadata_fetcher.fetch_by_issn = lambda **kwargs: calls.append(kwargs) or [{
            "title": "Nature metadata",
            "abstract": "General biology",
            "doi": "10.1038/nature.2026.001",
            "url": "https://doi.org/10.1038/nature.2026.001",
            "date": date(2026, 1, 15),
            "journal": "Nature",
        }]
        batches = []

        articles = parser.scrape_journal_stream(
            "Nature",
            "https://www.nature.com/nature",
            date(2026, 1, 1),
            date(2026, 1, 31),
            callback=lambda batch: batches.append(batch),
        )

        self.assertEqual(calls[0]["keywords"], None)
        self.assertEqual(len(articles), 1)
        self.assertEqual(batches[0][0]["doi"], "10.1038/nature.2026.001")

    def test_plos_crossref_batch_uses_stream_callback_without_keyword_query(self):
        class Agent:
            topic_name = "sleep"
            topic_keywords = ["sleep"]
            config = {"TOPIC_SEARCH_MAX_PAGES_PER_KEYWORD": 1}

        parser = PLOSParser(Agent())
        parser.set_current_journal_info({
            "name": "PLOS Digital Health",
            "link": "https://journals.plos.org/digitalhealth/",
            "source_row": {"EISSN": "2767-3170"},
        })
        calls = []
        parser.metadata_fetcher.fetch_by_issn = lambda **kwargs: calls.append(kwargs) or [{
            "title": "PLOS metadata",
            "abstract": "Digital health",
            "doi": "10.1371/journal.pdig.0001000",
            "url": "https://doi.org/10.1371/journal.pdig.0001000",
            "date": date(2026, 1, 15),
            "journal": "PLOS Digital Health",
        }]
        batches = []

        articles = parser.scrape_journal_stream(
            "PLOS Digital Health",
            "https://journals.plos.org/digitalhealth/",
            date(2026, 1, 1),
            date(2026, 1, 31),
            callback=lambda batch: batches.append(batch),
        )

        self.assertEqual(calls[0]["keywords"], None)
        self.assertEqual(len(articles), 1)
        self.assertEqual(batches[0][0]["doi"], "10.1371/journal.pdig.0001000")

    def test_cell_crossref_stats_list_returns_metadata_without_topic_filter(self):
        class Agent:
            topic_name = "sleep"
            topic_keywords = ["sleep"]
            config = {"TOPIC_SEARCH_MAX_PAGES_PER_KEYWORD": 1}

        parser = CellParser(Agent())
        parser.set_current_journal_info({
            "name": "Cancer Cell",
            "link": "https://www.cell.com/cancer-cell/home",
            "source_row": {"ISSN": "1535-6108"},
        })
        parser.metadata_fetcher.last_keyword_stats = [{
            "issn": "1535-6108",
            "keyword": "sleep",
            "fetched": 2,
            "added": 2,
        }]
        parser.metadata_fetcher.fetch_by_issn = lambda **kwargs: [
            {
                "title": "Cancer signaling",
                "abstract": "Oncology mechanisms.",
                "doi": "10.1016/j.ccell.2026.01.001",
                "url": "https://doi.org/10.1016/j.ccell.2026.01.001",
                "date": date(2026, 1, 15),
                "journal": "Cancer Cell",
            },
            {
                "title": "Tumor metabolism",
                "abstract": "Metabolic regulation.",
                "doi": "10.1016/j.ccell.2026.01.002",
                "url": "https://doi.org/10.1016/j.ccell.2026.01.002",
                "date": date(2026, 1, 16),
                "journal": "Cancer Cell",
            },
        ]

        articles = parser.scrape_journal(
            "Cancer Cell",
            "https://www.cell.com/cancer-cell/home",
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["doi"], "10.1016/j.ccell.2026.01.001")

    def test_factory_uses_main_cell_parser(self):
        parser = create_parser("cell", None)

        self.assertEqual(parser.__class__.__module__, "parser.cell")


if __name__ == "__main__":
    unittest.main()
