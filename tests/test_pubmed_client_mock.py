from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.pubmed_client import PubMedClient
from sleep_ai_scientist.api.rate_limiter import RateLimiter
from tests.api_test_utils import FakeSession


def test_pubmed_client_mock_parses_records():
    session = FakeSession([
        {"esearchresult": {"idlist": ["123"]}},
        {"result": {"uids": ["123"], "123": {"title": "Insomnia slow waves", "pubdate": "2020 Jan", "fulljournalname": "Sleep", "articleids": [{"idtype": "doi", "value": "10.1/a"}], "authors": [{"name": "A B"}]}}},
    ])
    base = BaseAPIClient("pubmed", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils", session=session, rate_limiter=RateLimiter(enabled=False))
    result = PubMedClient(base, {}).search("insomnia", 1)
    assert result.count == 1
    assert result.records[0].pmid == "123"
    assert result.records[0].doi == "10.1/a"
    assert result.records[0].year == 2020

