import yaml

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline
from tests.api_test_utils import fake_online_literature_search


def test_grounding_pipeline_llm_disabled_rule_only(monkeypatch, tmp_path):
    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fake_online_literature_search)
    config = load_config("configs/grounding_config.yaml")
    config.pop("_config_path", None)
    config.pop("_project_root", None)
    config["paths"].update({"output_grounding_dir": str(tmp_path / "grounding"), "output_profiles_dir": str(tmp_path / "profiles"), "report_path": str(tmp_path / "phase1_grounding_report.md"), "literature_registry_csv": str(tmp_path / "registry.csv"), "literature_registry_jsonl": str(tmp_path / "registry.jsonl"), "literature_deduplication_report": str(tmp_path / "dedup.csv"), "corpus_manifest": str(tmp_path / "manifest.json")})
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    result = run_grounding_pipeline(path)
    assert result["evidence"] > 0
    assert (tmp_path / "grounding" / "evidence_extraction_audit.json").exists()
