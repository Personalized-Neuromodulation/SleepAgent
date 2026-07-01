from sleep_ai_scientist.literature.library_builder import run_literature_build


def test_literature_build_offline_mock_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "library.db"))
    result = run_literature_build(
        "configs/literature_library_config.yaml",
        query_config_path="configs/sleep_literature_queries.yaml",
        library_version="test_library",
        backend="sqlite",
        api_enabled=False,
    )
    assert result["registry_records"] >= 3
    assert result["query_set_version"] == "sleep_literature_queries_v2_broad_sleep_science"

