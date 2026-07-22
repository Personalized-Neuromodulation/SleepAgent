from __future__ import annotations

from sleep_ai_scientist.schemas.literature import LiteratureRecord


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")


class FakeSession:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params or {}, "headers": headers or {}, "timeout": timeout})
        return FakeResponse(self.responses.pop(0) if self.responses else {})


def fake_online_literature_search(config):
    return [
        LiteratureRecord(
            paper_id="api_online_001",
            title="Insomnia slow wave and thalamocortical coupling",
            abstract=(
                "In 42 insomnia participants, reduced slow wave activity and lower "
                "slow_wave_density were associated with altered thalamocortical connectivity, "
                "thalamus_DMN_FC, and insomnia severity measured by ISI."
            ),
            year=2024,
            source="api:mock",
            provider="mock_provider",
            query="insomnia slow wave EEG",
        )
    ], {
        "enabled": True,
        "provider_counts": {"mock_provider": 1},
        "query_results": [{"provider": "mock_provider", "query": "insomnia slow wave EEG", "result_count": 1}],
        "query_count": 1,
        "raw_count": 1,
        "deduplicated_count": 1,
        "warnings": [],
    }
