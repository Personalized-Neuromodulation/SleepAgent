import os

from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.rate_limiter import RateLimiter
from sleep_ai_scientist.api.semantic_scholar_client import SemanticScholarClient
from tests.api_test_utils import FakeSession


def test_semantic_scholar_client_mock_uses_api_key(monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "secret")
    session = FakeSession([{"data": [{"paperId": "S1", "title": "Insomnia", "abstract": "EEG", "year": 2023, "authors": [{"name": "A B"}], "venue": "Sleep", "externalIds": {"DOI": "10.1/a", "PubMed": "123"}, "citationCount": 4, "url": "https://s2", "isOpenAccess": True}]}])
    base = BaseAPIClient("semantic_scholar", "https://example.org/graph/v1", session=session, rate_limiter=RateLimiter(enabled=False))
    result = SemanticScholarClient(base, {}).search("insomnia", 1)
    assert session.calls[0]["headers"]["x-api-key"] == "secret"
    assert result.records[0].doi == "10.1/a"
    assert result.records[0].pmid == "123"
