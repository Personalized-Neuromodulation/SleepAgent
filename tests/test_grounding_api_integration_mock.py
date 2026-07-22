from pathlib import Path

import yaml

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.common.io import ensure_parent
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_grounding_api_integration_mock(monkeypatch, tmp_path):
    config = load_config("configs/grounding_config.yaml")
    config.pop("_config_path", None)
    config.pop("_project_root", None)
    config.setdefault("api", {})["enabled"] = True
    config["api"]["cache_dir"] = str(tmp_path / "cache")
    config["api"]["output"] = {
        "api_literature_csv": str(tmp_path / "api_retrieved_papers.csv"),
        "api_literature_jsonl": str(tmp_path / "api_retrieved_papers.jsonl"),
        "api_search_log": str(tmp_path / "api_search_log.jsonl"),
    }
    config["paths"].update(
        {
            "output_grounding_dir": str(tmp_path / "grounding"),
            "output_profiles_dir": str(tmp_path / "profiles"),
            "report_path": str(tmp_path / "reports" / "grounding_report.md"),
            "phase1_report_path": str(tmp_path / "reports" / "phase1_grounding_report.md"),
            "literature_registry_csv": str(tmp_path / "literature_registry.csv"),
            "literature_registry_jsonl": str(tmp_path / "literature_registry.jsonl"),
            "literature_deduplication_report": str(tmp_path / "literature_deduplication_report.csv"),
            "corpus_manifest": str(tmp_path / "corpus_manifest.json"),
            "api_literature_csv": str(tmp_path / "api_retrieved_papers.csv"),
            "api_literature_jsonl": str(tmp_path / "api_retrieved_papers.jsonl"),
            "api_search_log": str(tmp_path / "api_search_log.jsonl"),
        }
    )
    config_path = tmp_path / "grounding_api.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    def fake_search(config):
        csv_path = Path(config["api"]["output"]["api_literature_csv"])
        jsonl_path = Path(config["api"]["output"]["api_literature_jsonl"])
        log_path = Path(config["api"]["output"]["api_search_log"])
        ensure_parent(csv_path).write_text("paper_id,title,abstract,year,doi,pmid,source,keywords,url,notes\napi1,API slow wave paper,insomnia slow wave thalamocortical ISI,2024,10.1/api,,api:mock,slow wave,,mock\n", encoding="utf-8")
        ensure_parent(jsonl_path).write_text('{"paper_id":"api1"}\n', encoding="utf-8")
        ensure_parent(log_path).write_text('{"provider":"mock","success":true}\n', encoding="utf-8")
        return [
            LiteratureRecord(
                paper_id="api1",
                title="API slow wave paper",
                abstract="insomnia slow wave thalamocortical ISI",
                year=2024,
                doi="10.1/api",
                pmid="",
                source="api:mock",
                keywords=["slow wave"],
                url="",
                notes="mock",
            )
        ], {"enabled": True, "provider_counts": {"mock": 1}, "query_count": 1, "raw_count": 1, "deduplicated_count": 1, "warnings": [], "cache_enabled": True, "cache_dir": str(tmp_path / "cache")}

    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fake_search)
    result = run_grounding_pipeline(config_path)
    assert Path(config["api"]["output"]["api_literature_csv"]).exists()
    assert Path(config["api"]["output"]["api_search_log"]).exists()
    assert result["api_papers"] == 1
    assert result["papers"] == 1
