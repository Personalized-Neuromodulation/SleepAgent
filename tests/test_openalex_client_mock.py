from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.openalex_client import OpenAlexClient
from sleep_ai_scientist.api.rate_limiter import RateLimiter
from tests.api_test_utils import FakeSession


def test_openalex_client_mock_restores_abstract():
    payload = {"results": [{"id": "W1", "doi": "10.1/a", "display_name": "Insomnia", "publication_year": 2022, "cited_by_count": 5, "abstract_inverted_index": {"slow": [0], "wave": [1]}, "authorships": [{"author": {"display_name": "A B"}}], "primary_location": {"source": {"display_name": "Sleep"}}, "open_access": {"is_oa": True}}]}
    base = BaseAPIClient("openalex", "https://example.org", session=FakeSession([payload]), rate_limiter=RateLimiter(enabled=False))
    result = OpenAlexClient(base, {}).search("insomnia", 1)
    rec = result.records[0]
    assert rec.abstract == "slow wave"
    assert rec.year == 2022
    assert rec.citation_count == 5

