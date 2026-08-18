import unittest

from parser.metadata_merge import merge_metadata_rows


class MetadataMergeTests(unittest.TestCase):
    def test_merge_prefers_complete_fields_and_combines_sources(self):
        existing = [{
            "title": "Sleep paper",
            "abstract": "",
            "date": "2026-01-01",
            "doi": "10.1000/sleep",
            "link": "",
            "authors": "",
            "journal": "Example Journal",
            "source": "crossref",
        }]
        discovered = [{
            "title": "Sleep paper",
            "abstract": "A detailed sleep abstract.",
            "date": "2026-01-01",
            "doi": "https://doi.org/10.1000/sleep",
            "url": "https://example.org/sleep",
            "authors": "Ada Lovelace",
            "journal": "Example Journal",
            "source": "openalex",
        }]

        merged = merge_metadata_rows(existing, discovered)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["abstract"], "A detailed sleep abstract.")
        self.assertEqual(merged[0]["authors"], "Ada Lovelace")
        self.assertEqual(merged[0]["link"], "https://example.org/sleep")
        self.assertEqual(merged[0]["source"], "crossref;openalex")

    def test_merge_dedupes_title_date_when_doi_missing(self):
        existing = [{
            "title": "Circadian rhythm study",
            "date": "2026-03-02",
            "journal": "Example Journal",
            "abstract": "",
            "source": "publisher",
        }]
        discovered = [{
            "title": "  Circadian   rhythm study ",
            "date": "2026-03-02",
            "journal": "Example Journal",
            "abstract": "Circadian sleep abstract.",
            "source": "europe_pmc",
        }]

        merged = merge_metadata_rows(existing, discovered)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["abstract"], "Circadian sleep abstract.")
        self.assertEqual(merged[0]["source"], "publisher;europe_pmc")


if __name__ == "__main__":
    unittest.main()
