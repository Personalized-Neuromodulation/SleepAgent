from __future__ import annotations

from sleep_ai_scientist.api import literature_client
from sleep_ai_scientist.schemas.api import APISearchResult
from sleep_ai_scientist.schemas.literature import LiteratureRecord


class FakeClient:
    def __init__(self, provider: str):
        self.provider = provider
        self.base = type("Base", (), {"logs": []})()

    def search(self, query: str, *, max_results: int):
        return APISearchResult(provider=self.provider, query=query, count=1, records=[], warnings=[])


def test_search_literature_apis_uses_compact_progress_in_verbose_mode(tmp_path, monkeypatch, capsys):
    config = {
        "_project_root": str(tmp_path),
        "api": {
            "enabled": True,
            "verbose": True,
            "progress": True,
            "progress_update_every": 2,
            "max_results_per_query": 3,
            "providers": {"pubmed": {"enabled": True, "base_url": "https://example.test"}},
            "output": {
                "api_literature_csv": str(tmp_path / "papers.csv"),
                "api_literature_jsonl": str(tmp_path / "papers.jsonl"),
                "api_search_log": str(tmp_path / "api_log.jsonl"),
            },
            "search_queries": ["query one", "query two", "query three", "query four"],
        },
    }
    monkeypatch.setattr(literature_client, "build_client", lambda provider, config, session=None, rate_limit_enabled=True: FakeClient(provider))
    monkeypatch.setattr(literature_client, "deduplicate_api_records", lambda records: records)
    monkeypatch.setattr(literature_client, "api_to_literature_record", lambda item: LiteratureRecord(paper_id="x", title="x"))

    literature_client.search_literature_apis(config)

    out = capsys.readouterr().out
    assert "[api:pubmed]" in out
    assert "4/4" in out
    assert "query one" not in out
    assert "query two" not in out
    assert out.count("[api:pubmed]") == 1


def test_search_literature_apis_writes_csv_without_jsonl_exports(tmp_path, monkeypatch):
    config = {
        "_project_root": str(tmp_path),
        "api": {
            "enabled": True,
            "verbose": False,
            "progress": False,
            "max_results_per_query": 3,
            "providers": {"pubmed": {"enabled": True, "base_url": "https://example.test"}},
            "output": {
                "api_literature_csv": str(tmp_path / "papers.csv"),
                "api_literature_jsonl": str(tmp_path / "papers.jsonl"),
                "api_search_log": str(tmp_path / "api_log.jsonl"),
            },
            "search_queries": ["query one"],
        },
    }
    monkeypatch.setattr(literature_client, "build_client", lambda provider, config, session=None, rate_limit_enabled=True: FakeClient(provider))
    monkeypatch.setattr(literature_client, "deduplicate_api_records", lambda records: records)

    literature_client.search_literature_apis(config)

    assert (tmp_path / "papers.csv").exists()
    assert not (tmp_path / "papers.jsonl").exists()
    assert not (tmp_path / "api_log.jsonl").exists()
