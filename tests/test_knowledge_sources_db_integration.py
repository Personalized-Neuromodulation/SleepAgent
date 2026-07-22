from sleep_ai_scientist.knowledge_sources.registry_builder import build_knowledge_sources


def test_knowledge_sources_build_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "knowledge.db"))
    result = build_knowledge_sources("configs/knowledge_sources_config.yaml", backend="sqlite")
    assert result["guidelines_count"] > 0
    assert result["standards_count"] > 0
    assert result["datasets_count"] > 0
    assert result["instruments_count"] > 0

