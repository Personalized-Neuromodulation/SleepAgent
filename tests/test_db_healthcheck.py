from sleep_ai_scientist.storage.healthcheck import check_database_connection


def test_db_healthcheck_sqlite_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "health.db"))
    result = check_database_connection("configs/database_config.yaml", backend="sqlite")
    assert result["ok"] is True
    assert "sqlite" in result["database_url_masked"]

