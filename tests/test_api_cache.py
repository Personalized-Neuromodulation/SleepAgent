from sleep_ai_scientist.api.base import BaseAPIClient
from sleep_ai_scientist.api.cache import APICache
from sleep_ai_scientist.api.rate_limiter import RateLimiter
from tests.api_test_utils import FakeSession


def test_api_cache_hit_skips_network(tmp_path):
    cache = APICache(tmp_path, enabled=True)
    session = FakeSession([{"ok": True}])
    client = BaseAPIClient("provider", "https://example.org", cache=cache, rate_limiter=RateLimiter(enabled=False), session=session)
    first = client.get("search", {"q": "x"})
    second = client.get("search", {"q": "x"})
    assert first == {"ok": True}
    assert second == {"ok": True}
    assert len(session.calls) == 1
    assert client.logs[-1].cached is True

