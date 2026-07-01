from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.rate_limiter import RateLimiter
from tests.api_test_utils import FakeSession


def test_api_base_get_logs_success():
    session = FakeSession([{"result": 1}])
    client = BaseAPIClient("provider", "https://example.org", rate_limiter=RateLimiter(enabled=False), session=session)
    payload = client.get("endpoint", {"q": "test"}, query="test")
    assert payload == {"result": 1}
    assert client.logs[0].success is True
    assert session.calls[0]["timeout"] == 20

