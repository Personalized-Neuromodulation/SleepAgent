from sleep_ai_scientist.storage.db import create_engine_from_config, init_database
from sleep_ai_scientist.storage.healthcheck import check_database_connection


def test_sqlite_db_init_and_healthcheck():
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    result = check_database_connection("configs/database_config.yaml", backend="sqlite")
    assert result["ok"] is True
    assert result["backend"] == "sqlite"
    assert result["table_count"] >= 9
    engine.dispose()

