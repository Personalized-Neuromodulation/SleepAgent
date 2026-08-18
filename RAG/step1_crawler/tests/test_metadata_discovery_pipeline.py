import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import ALL_INFO_FIELDS, CrawlerSystem


class Config:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeDiscovery:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def discover(self, keywords, start_date, end_date):
        self.calls.append({
            "keywords": keywords,
            "start_date": start_date,
            "end_date": end_date,
            "kwargs": self.kwargs,
        })
        return [
            {
                "title": "Existing sleep paper",
                "abstract": "Recovered abstract from discovery.",
                "date": "2026-01-02",
                "doi": "10.1000/existing",
                "url": "https://example.org/existing",
                "authors": "Ada Lovelace",
                "journal": "Example Journal",
                "source": "openalex",
            },
            {
                "title": "New insomnia paper",
                "abstract": "Insomnia discovery abstract.",
                "date": "2025-05-05",
                "doi": "10.1000/new",
                "url": "https://example.org/new",
                "journal": "Example Journal",
                "source": "semantic_scholar",
            },
        ]


class MetadataDiscoveryPipelineTests(unittest.TestCase):
    def test_discovery_merges_into_all_info_before_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            all_info = Path(tmpdir) / "all_info.csv"
            with all_info.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=ALL_INFO_FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerow({
                    "title": "Existing sleep paper",
                    "abstract": "",
                    "date": "2026-01-02",
                    "doi": "10.1000/existing",
                    "journal": "Example Journal",
                    "source": "crossref",
                })

            system = CrawlerSystem.__new__(CrawlerSystem)
            system.config_manager = Config({
                "METADATA_DISCOVERY_ENABLED": True,
                "METADATA_DISCOVERY_YEARS": 5,
                "METADATA_DISCOVERY_SOURCES": ["openalex", "semantic_scholar"],
                "METADATA_DISCOVERY_ROWS": 2,
                "METADATA_DISCOVERY_MAX_PAGES_PER_KEYWORD": 1,
                "METADATA_DISCOVERY_TIMEOUT_SECONDS": 3,
                "METADATA_DISCOVERY_MIN_INTERVAL_SECONDS": 0,
            })
            system.saved_files = []

            agent = type("Agent", (), {"topic_keywords": ["sleep", "insomnia"]})()
            FakeDiscovery.calls = []

            with patch("main.MetadataDiscoveryService", FakeDiscovery):
                stats = system._discover_and_merge_all_info_csv(
                    str(all_info),
                    "other",
                    "Example Journal",
                    agent,
                    "2026-01-01",
                    "2026-12-31",
                )

            rows = list(csv.DictReader(all_info.open(encoding="utf-8-sig", newline="")))

        self.assertEqual(stats["discovered"], 2)
        self.assertEqual(stats["metadata_merged_existing"], 1)
        self.assertEqual(stats["metadata_discovery_added"], 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["abstract"], "Recovered abstract from discovery.")
        self.assertEqual(rows[0]["source"], "crossref;openalex")
        self.assertEqual(rows[1]["doi"], "10.1000/new")
        self.assertEqual(FakeDiscovery.calls[0]["start_date"], "2022-01-01")
        self.assertEqual(FakeDiscovery.calls[0]["end_date"], "2026-12-31")
        self.assertEqual(FakeDiscovery.calls[0]["kwargs"]["journal_name"], "Example Journal")


if __name__ == "__main__":
    unittest.main()
