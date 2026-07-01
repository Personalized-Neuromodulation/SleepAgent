from pathlib import Path

import yaml

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.common.io import ensure_parent
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def _tmp_grounding_config(tmp_path: Path) -> Path:
    config = load_config("configs/grounding_config.yaml")
    config.pop("_config_path", None)
    config.pop("_project_root", None)
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
    config.setdefault("api", {})["enabled"] = True
    config["api"]["cache_dir"] = str(tmp_path / "cache")
    config["api"]["output"] = {
        "api_literature_csv": str(tmp_path / "api_retrieved_papers.csv"),
        "api_literature_jsonl": str(tmp_path / "api_retrieved_papers.jsonl"),
        "api_search_log": str(tmp_path / "api_search_log.jsonl"),
    }
    path = tmp_path / "grounding.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_grounding_api_build_generates_versioned_corpus(monkeypatch, tmp_path):
    config_path = _tmp_grounding_config(tmp_path)
    query_config = tmp_path / "queries.yaml"
    query_config.write_text(
        yaml.safe_dump(
            {
                "query_set": {"version": "test_queries_v1"},
                "queries": {"core": ["insomnia slow wave EEG"]},
                "settings": {"max_results_per_query": 2, "providers": ["pubmed"]},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    def fake_search(config):
        csv_path = Path(config["api"]["output"]["api_literature_csv"])
        jsonl_path = Path(config["api"]["output"]["api_literature_jsonl"])
        log_path = Path(config["api"]["output"]["api_search_log"])
        ensure_parent(csv_path).write_text(
            "paper_id,title,abstract,year,doi,pmid,pmcid,source,provider,provider_id,journal,authors,url,keywords,citation_count,retrieved_at,query,raw_source_available\n"
            "api1,API slow wave paper,insomnia slow wave associated with ISI,2024,10.1/api,,,api:pubmed,pubmed,1,J,A,u,slow wave,3,now,insomnia slow wave EEG,true\n",
            encoding="utf-8",
        )
        ensure_parent(jsonl_path).write_text('{"paper_id":"api1"}\n', encoding="utf-8")
        ensure_parent(log_path).write_text('{"provider":"pubmed","success":true}\n', encoding="utf-8")
        return [
            LiteratureRecord(
                paper_id="api1",
                title="API slow wave paper",
                abstract="insomnia slow wave associated with ISI",
                year=2024,
                doi="10.1/api",
                source="api:pubmed",
                keywords=["slow wave"],
            )
        ], {
            "enabled": True,
            "provider_counts": {"pubmed": 1},
            "query_results": [{"provider": "pubmed", "query": "insomnia slow wave EEG", "retrieved_at": "now", "result_count": 1}],
            "query_count": 1,
            "raw_count": 1,
            "deduplicated_count": 1,
            "warnings": [],
            "cache_enabled": True,
            "cache_dir": str(tmp_path / "cache"),
        }

    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fake_search)

    result = run_grounding_pipeline(config_path, query_config_path=query_config, corpus_version="test_corpus_v1")

    assert result["corpus_version"] == "test_corpus_v1"
    for path in [
        tmp_path / "api_retrieved_papers.csv",
        tmp_path / "literature_registry.csv",
        tmp_path / "literature_registry.jsonl",
        tmp_path / "corpus_manifest.json",
        tmp_path / "grounding" / "evidence_table.csv",
        tmp_path / "grounding" / "mechanism_graph.json",
        tmp_path / "grounding" / "evidence_to_variable_map.yaml",
        tmp_path / "grounding" / "grounding_qc_report.json",
    ]:
        assert path.exists()


def test_grounding_api_fail_open_fallback(monkeypatch, tmp_path):
    config_path = _tmp_grounding_config(tmp_path)

    def fake_search(config):
        return [], {"enabled": True, "provider_counts": {}, "query_count": 1, "raw_count": 0, "deduplicated_count": 0, "warnings": ["pubmed failed"], "cache_enabled": False}

    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fake_search)

    result = run_grounding_pipeline(config_path, corpus_version="fallback_corpus_v1")

    assert result["api_papers"] == 0
    assert (tmp_path / "corpus_manifest.json").exists()
