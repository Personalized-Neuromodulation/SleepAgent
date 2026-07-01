from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.europe_pmc_client import EuropePMCClient
from sleep_ai_scientist.api.rate_limiter import RateLimiter
from tests.api_test_utils import FakeSession


def test_europe_pmc_client_mock_parses_records():
    session = FakeSession([{"resultList": {"result": [{"id": "1", "pmid": "123", "pmcid": "PMC1", "doi": "10.1/a", "title": "Insomnia", "abstractText": "slow wave", "journalTitle": "Sleep", "pubYear": "2021", "authorString": "A B, C D", "citedByCount": "7", "isOpenAccess": "Y"}]}}])
    base = BaseAPIClient("europe_pmc", "https://example.org", session=session, rate_limiter=RateLimiter(enabled=False))
    result = EuropePMCClient(base, {}).search("insomnia", 1)
    rec = result.records[0]
    assert rec.abstract == "slow wave"
    assert rec.pmcid == "PMC1"
    assert rec.citation_count == 7

