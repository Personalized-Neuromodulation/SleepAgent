import tempfile
import unittest
from pathlib import Path

import main as main_module
from crawl_checkpoint import article_key, normalize_article_key
from main import CrawlerSystem


class FakeAgent:
    topic_name = "sleep"
    topic_keywords = ["sleep"]
    last_error_reason = ""

    def __init__(self, related=False):
        self.contents = []
        self.related = related

    def batch_analyze_papers_in_batches_concurrent(self, contents):
        self.contents = contents
        return [
            {
                "id": item["id"],
                "judgment": "Related" if self.related else "No",
                "is_ai_related": self.related,
                "explanation": "matched by LLM" if self.related else "",
            }
            for item in contents
        ]


class FakeRepairParser:
    def __init__(self):
        self.calls = []

    def repair_article_from_url(self, article, journal_name):
        self.calls.append((article.get("link"), journal_name))
        repaired = dict(article)
        repaired["abstract"] = "Sleep architecture and insomnia outcomes."
        return repaired


class ResumeCheckpointTests(unittest.TestCase):
    def test_article_key_normalizes_doi_urls(self):
        self.assertEqual(
            article_key({"doi": "https://doi.org/10.1371/journal.pdig.0001460"}),
            article_key({"doi": "10.1371/journal.pdig.0001460"}),
        )
        self.assertEqual(
            article_key({"link": "https://journals.plos.org/digitalhealth/article?id=10.1371/journal.pdig.0001460"}),
            article_key({"doi": "10.1371/journal.pdig.0001460"}),
        )
        self.assertEqual(
            normalize_article_key("doi:https://doi.org/10.1371/journal.pdig.0001460"),
            "doi:10.1371/journal.pdig.0001460",
        )

    def test_review_exports_all_info_and_llm_related_after_keyword_prefilter(self):
        crawler = CrawlerSystem()
        agent = FakeAgent(related=True)
        with tempfile.TemporaryDirectory() as tmp:
            old_exports_dir = main_module.EXPORTS_DIR
            main_module.EXPORTS_DIR = Path(tmp)
            crawler.config_manager.get = lambda key, default=None: default
            try:
                result = crawler.review_and_export_papers(
                    [
                        {"title": "Sleep paper", "abstract": "sleep", "doi": "10.1000/sleep", "url": "https://example.org/sleep"},
                        {"title": "Cancer paper", "abstract": "oncology", "doi": "10.1000/cancer", "url": "https://example.org/cancer"},
                    ],
                    "other",
                    "Example Journal",
                    agent,
                    "2026-01-01",
                    "2026-01-31",
                    "csv",
                )
                all_info = Path(tmp) / "sleep" / "other" / "Example Journal" / "all_info.csv"
                related = Path(tmp) / "sleep" / "other" / "Example Journal" / "sleep_related_2026-01-01_2026-01-31.csv"
                self.assertTrue(all_info.exists())
                self.assertTrue(related.exists())
            finally:
                main_module.EXPORTS_DIR = old_exports_dir

        self.assertEqual([item["title"] for item in agent.contents], ["Sleep paper"])
        self.assertEqual(result["candidate"], 2)
        self.assertEqual(result["related"], 1)
        self.assertEqual(result["reviewed"], 1)

    def test_empty_abstract_is_repaired_after_all_info_for_related_export(self):
        crawler = CrawlerSystem()
        agent = FakeAgent(related=True)
        parser = FakeRepairParser()
        crawler.parsers["other"] = parser
        with tempfile.TemporaryDirectory() as tmp:
            old_exports_dir = main_module.EXPORTS_DIR
            main_module.EXPORTS_DIR = Path(tmp)
            crawler.config_manager.get = lambda key, default=None: default
            try:
                result = crawler.review_and_export_papers(
                    [
                        {
                            "title": "Sleep biomarker paper",
                            "abstract": "",
                            "doi": "10.1000/repair",
                            "url": "https://example.org/repair",
                        },
                    ],
                    "other",
                    "Example Journal",
                    agent,
                    "2026-01-01",
                    "2026-01-31",
                    "csv",
                )
                all_info = Path(tmp) / "sleep" / "other" / "Example Journal" / "all_info.csv"
                related = Path(tmp) / "sleep" / "other" / "Example Journal" / "sleep_related_2026-01-01_2026-01-31.csv"
                all_text = all_info.read_text(encoding="utf-8-sig")
                related_text = related.read_text(encoding="utf-8-sig")
            finally:
                main_module.EXPORTS_DIR = old_exports_dir

        self.assertEqual(result["related"], 1)
        self.assertEqual(result["reviewed"], 1)
        self.assertEqual(len(parser.calls), 1)
        self.assertNotIn("Sleep architecture and insomnia outcomes.", all_text)
        self.assertIn("Sleep architecture and insomnia outcomes.", related_text)
        self.assertEqual(agent.contents[0]["abstract"], "Sleep architecture and insomnia outcomes.")

    def test_title_without_keyword_can_match_after_abstract_repair(self):
        crawler = CrawlerSystem()
        agent = FakeAgent(related=True)
        parser = FakeRepairParser()
        crawler.parsers["other"] = parser
        with tempfile.TemporaryDirectory() as tmp:
            old_exports_dir = main_module.EXPORTS_DIR
            main_module.EXPORTS_DIR = Path(tmp)
            crawler.config_manager.get = lambda key, default=None: default
            try:
                result = crawler.review_and_export_papers(
                    [
                        {
                            "title": "Restless legs syndrome",
                            "abstract": "",
                            "doi": "10.1000/restless",
                            "url": "https://example.org/restless",
                        },
                    ],
                    "other",
                    "Example Journal",
                    agent,
                    "2026-01-01",
                    "2026-01-31",
                    "csv",
                )
                all_info = Path(tmp) / "sleep" / "other" / "Example Journal" / "all_info.csv"
                related = Path(tmp) / "sleep" / "other" / "Example Journal" / "sleep_related_2026-01-01_2026-01-31.csv"
                all_text = all_info.read_text(encoding="utf-8-sig")
                related_text = related.read_text(encoding="utf-8-sig")
            finally:
                main_module.EXPORTS_DIR = old_exports_dir

        self.assertEqual(result["prefiltered"], 1)
        self.assertEqual(result["reviewed"], 1)
        self.assertEqual(result["related"], 1)
        self.assertEqual(len(parser.calls), 1)
        self.assertNotIn("Sleep architecture and insomnia outcomes.", all_text)
        self.assertIn("Restless legs syndrome", related_text)

    def test_empty_abstract_without_expanded_title_match_is_not_repaired(self):
        crawler = CrawlerSystem()
        agent = FakeAgent(related=True)
        parser = FakeRepairParser()
        crawler.parsers["other"] = parser
        with tempfile.TemporaryDirectory() as tmp:
            old_exports_dir = main_module.EXPORTS_DIR
            main_module.EXPORTS_DIR = Path(tmp)
            crawler.config_manager.get = lambda key, default=None: default
            try:
                result = crawler.review_and_export_papers(
                    [
                        {
                            "title": "General oncology mechanism",
                            "abstract": "",
                            "doi": "10.1000/general",
                            "url": "https://example.org/general",
                        },
                    ],
                    "other",
                    "Example Journal",
                    agent,
                    "2026-01-01",
                    "2026-01-31",
                    "csv",
                )
            finally:
                main_module.EXPORTS_DIR = old_exports_dir

        self.assertEqual(result["prefiltered"], 0)
        self.assertEqual(result["reviewed"], 0)
        self.assertEqual(result["related"], 0)
        self.assertEqual(len(parser.calls), 0)

    def test_existing_all_info_is_deduped_when_appending(self):
        crawler = CrawlerSystem()
        agent = FakeAgent()
        old_exports_dir = main_module.EXPORTS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            try:
                main_module.EXPORTS_DIR = Path(tmp)
                crawler.config_manager.get = lambda key, default=None: default

                for _ in range(2):
                    result = crawler.review_and_export_papers(
                        [{"title": "Old sleep paper", "abstract": "sleep", "doi": "10.1000/old", "url": "https://example.org/old"}],
                        "other",
                        "Example Journal",
                        agent,
                        "2026-01-01",
                        "2026-01-31",
                        "csv",
                    )

                all_info = Path(tmp) / "sleep" / "other" / "Example Journal" / "all_info.csv"
                rows = all_info.read_text(encoding="utf-8-sig").splitlines()
            finally:
                main_module.EXPORTS_DIR = old_exports_dir

        self.assertEqual(result["prefiltered"], 1)
        self.assertEqual(result["reviewed"], 1)
        self.assertEqual(result["related"], 0)
        self.assertEqual(len(rows), 2)

    def test_related_export_is_deduped_by_title_even_with_different_doi(self):
        crawler = CrawlerSystem()
        agent = FakeAgent(related=True)
        old_exports_dir = main_module.EXPORTS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            try:
                main_module.EXPORTS_DIR = Path(tmp)
                crawler.config_manager.get = lambda key, default=None: default

                result = crawler.review_and_export_papers(
                    [
                        {
                            "title": "A gut-secreted peptide suppresses arousability from sleep",
                            "abstract": "sleep arousal",
                            "doi": "10.1016/j.cell.2023.02.022",
                            "url": "https://doi.org/10.1016/j.cell.2023.02.022",
                        },
                        {
                            "title": "A gut-secreted peptide suppresses arousability from sleep",
                            "abstract": "sleep arousal",
                            "doi": "10.1016/j.cell.2023.04.005",
                            "url": "https://doi.org/10.1016/j.cell.2023.04.005",
                        },
                    ],
                    "cell",
                    "Cell",
                    agent,
                    "2026-01-01",
                    "2026-01-31",
                    "csv",
                )

                related = Path(tmp) / "sleep" / "cell" / "Cell" / "sleep_related_2026-01-01_2026-01-31.csv"
                lines = related.read_text(encoding="utf-8-sig").splitlines()
            finally:
                main_module.EXPORTS_DIR = old_exports_dir

        self.assertEqual(result["related"], 1)
        self.assertEqual(result["saved"], 1)
        self.assertEqual(len(lines), 2)

    def test_checkpoint_db_is_split_by_journal_type_under_exports(self):
        old_exports_dir = main_module.EXPORTS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            try:
                main_module.EXPORTS_DIR = Path(tmp)
                crawler = CrawlerSystem()
                for journal in ("nature", "other"):
                    crawler.get_checkpoint_store(journal)
                self.assertTrue((Path(tmp) / "nature_crawl_checkpoint.db").exists())
                self.assertTrue((Path(tmp) / "other_crawl_checkpoint.db").exists())
                self.assertFalse((Path(tmp) / "crawl_checkpoint.db").exists())
            finally:
                main_module.EXPORTS_DIR = old_exports_dir


if __name__ == "__main__":
    unittest.main()
