import unittest
from datetime import date

from parser.metadata_discovery import MetadataDiscoveryService


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload
        self.url = "https://example.org/api"
        self.headers = {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({
            "url": url,
            "params": params or {},
            "headers": headers or {},
            "timeout": timeout,
        })
        if "crossref" in url:
            return FakeResponse({
                "message": {
                    "items": [{
                        "DOI": "10.1000/crossref",
                        "title": ["Crossref sleep paper"],
                        "abstract": "Sleep abstract.",
                        "container-title": ["Example Journal"],
                        "issued": {"date-parts": [[2026, 1, 2]]},
                    }]
                }
            })
        if "europepmc" in url:
            return FakeResponse({
                "resultList": {
                    "result": [{
                        "doi": "10.1000/epmc",
                        "title": "Europe PMC insomnia paper",
                        "abstractText": "Insomnia abstract.",
                        "firstPublicationDate": "2026-01-03",
                        "journalTitle": "Example Journal",
                    }]
                }
            })
        if "openalex" in url:
            return FakeResponse({
                "results": [{
                    "doi": "https://doi.org/10.1000/openalex",
                    "title": "OpenAlex circadian paper",
                    "publication_date": "2026-01-04",
                    "abstract_inverted_index": {"Circadian": [0], "abstract.": [1]},
                    "primary_location": {"source": {"display_name": "Example Journal"}},
                }]
            })
        return FakeResponse({
            "data": [{
                "externalIds": {"DOI": "10.1000/s2"},
                "title": "Semantic Scholar REM paper",
                "abstract": "REM sleep abstract.",
                "year": 2026,
                "venue": "Example Journal",
                "url": "https://semanticscholar.org/paper/1",
            }]
        })


class MetadataDiscoveryTests(unittest.TestCase):
    def test_fetches_enabled_sources_with_keywords_and_date_window(self):
        session = FakeSession()
        service = MetadataDiscoveryService(
            sources=["crossref", "europe_pmc", "openalex", "semantic_scholar"],
            rows=2,
            max_pages_per_keyword=1,
            min_interval=0,
            session=session,
        )

        with self.assertLogs("parser.metadata_discovery", level="INFO") as logs:
            rows = service.discover(
                keywords=["sleep"],
                start_date=date(2022, 1, 1),
                end_date=date(2026, 12, 31),
            )

        self.assertEqual(
            {row["source"] for row in rows},
            {"crossref", "europe_pmc", "openalex", "semantic_scholar"},
        )
        self.assertEqual(len(rows), 4)
        crossref_call = session.calls[0]
        self.assertIn("from-pub-date:2022-01-01", crossref_call["params"]["filter"])
        self.assertEqual(crossref_call["params"]["query"], "sleep")
        log_text = "\n".join(logs.output)
        self.assertIn("source=crossref keyword=sleep returned=1", log_text)
        self.assertIn("source=europe_pmc keyword=sleep returned=1", log_text)
        self.assertIn("source=openalex keyword=sleep returned=1", log_text)
        self.assertIn("source=semantic_scholar keyword=sleep returned=1", log_text)


if __name__ == "__main__":
    unittest.main()
