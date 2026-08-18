import unittest
from unittest.mock import patch

from parser.doi_abstract import DoiAbstractFetcher


class DoiAbstractFetcherTests(unittest.TestCase):
    def test_clean_text_removes_crossref_jats_tags(self):
        text = DoiAbstractFetcher.clean_text(
            "<jats:p><jats:bold>Abstract</jats:bold>: Sleep improves memory.</jats:p>"
        )

        self.assertEqual(text, "Sleep improves memory.")

    def test_clean_text_restores_common_scientific_symbol_replacements(self):
        self.assertEqual(
            DoiAbstractFetcher.clean_text(
                "HIF-1�� and BMAL1 in bone regeneration: crosstalk between hypoxia response and circadian rhythm"
            ),
            "HIF-1α and BMAL1 in bone regeneration: crosstalk between hypoxia response and circadian rhythm",
        )
        self.assertEqual(
            DoiAbstractFetcher.clean_text("REG�� regulates circadian clock by modulating BMAL1 protein stability"),
            "REGγ regulates circadian clock by modulating BMAL1 protein stability",
        )

    def test_openalex_inverted_index_to_abstract(self):
        fetcher = DoiAbstractFetcher()
        abstract = fetcher._openalex_abstract({
            "Sleep": [0],
            "regulates": [1],
            "memory.": [2],
        })

        self.assertEqual(abstract, "Sleep regulates memory.")

    def test_normalize_doi_from_url(self):
        self.assertEqual(
            DoiAbstractFetcher.normalize_doi("https://doi.org/10.1016/j.cell.2020.02.044."),
            "10.1016/j.cell.2020.02.044",
        )

    def test_default_api_keys_and_email_are_configured(self):
        with patch.dict("os.environ", {}, clear=True):
            fetcher = DoiAbstractFetcher()

        self.assertEqual(fetcher.mailto, "m1993615519@163.com")
        self.assertEqual(fetcher.openalex_api_key, "RbfrULWTgikcvf6HTt8K2P")
        self.assertEqual(fetcher.s2_api_key, "s2k-UBcTYeR1Wu6oLdOPEooueysXchKs0pu26A1Zv2vd")

    def test_environment_can_override_api_keys(self):
        with patch.dict("os.environ", {
            "CROSSREF_MAILTO": "override@example.com",
            "OPENALEX_API_KEY": "oa-env",
            "S2_API_KEY": "s2-env",
        }, clear=True):
            fetcher = DoiAbstractFetcher()

        self.assertEqual(fetcher.mailto, "override@example.com")
        self.assertEqual(fetcher.openalex_api_key, "oa-env")
        self.assertEqual(fetcher.s2_api_key, "s2-env")


if __name__ == "__main__":
    unittest.main()
