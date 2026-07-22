from sleep_ai_scientist.literature.library_builder import run_literature_build
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_literature_build_online_mock_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "library.db"))
    monkeypatch.setattr(
        "sleep_ai_scientist.literature.library_builder.search_literature_apis",
        lambda config, session=None, rate_limit_enabled=True: (
            [
                LiteratureRecord(
                    paper_id="api_online_001",
                    title="Online API sleep paper",
                    abstract="Online insomnia slow wave EEG retrieval result.",
                    year=2025,
                    source="api:mock",
                    provider="mock_provider",
                    query="insomnia slow wave EEG",
                )
            ],
            {"enabled": True, "warnings": []},
        ),
    )
    result = run_literature_build(
        "configs/literature_library_config.yaml",
        query_config_path="configs/sleep_literature_queries.yaml",
        library_version="test_library",
        backend="sqlite",
        api_enabled=True,
    )
    assert result["registry_records"] == 1
    assert result["api_papers"] == 1
    assert result["query_set_version"] == "sleep_literature_queries_v2_broad_sleep_science"
