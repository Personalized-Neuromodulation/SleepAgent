import os

import pytest

from sleep_ai_scientist.storage.db import create_engine_from_config, init_database
from sleep_ai_scientist.storage.healthcheck import check_database_connection


@pytest.mark.postgres_live
def test_postgres_storage_live():
    if os.getenv("SLEEPAGENT_ENABLE_POSTGRES_LIVE_TESTS") != "true" or not os.getenv("SLEEPAGENT_DATABASE_URL"):
        pytest.skip("PostgreSQL live tests require opt-in env vars")
    engine = create_engine_from_config("configs/database_config.yaml", backend="postgresql")
    init_database(engine)
    result = check_database_connection("configs/database_config.yaml", backend="postgresql")
    assert result["ok"] is True
    engine.dispose()

