import os

import pytest

from sleep_ai_scientist.api.literature_client import build_client
from sleep_ai_scientist.common.config import load_config


pytestmark = pytest.mark.api_live


def test_europe_pmc_live_small_query():
    if os.getenv("SLEEPAGENT_ENABLE_LIVE_API_TESTS", "false").lower() != "true":
        pytest.skip("live API tests disabled")
    config = load_config("configs/grounding_config.yaml")
    config["api"]["enabled"] = True
    result = build_client("europe_pmc", config).search("insomnia slow wave EEG", 3)
    assert result.provider == "europe_pmc"
    assert result.records is not None
