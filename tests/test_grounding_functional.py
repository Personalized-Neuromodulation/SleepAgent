from pathlib import Path

import yaml

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.common.io import read_csv, read_yaml
from sleep_ai_scientist.foundation.foundation_pipeline import run_foundation_pipeline
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline
from tests.api_test_utils import fake_online_literature_search
from tests.config_helpers import toy_foundation_config_path


def _tmp_config(tmp_path: Path) -> Path:
    config = load_config("configs/grounding_config.yaml")
    config.pop("_config_path", None)
    config.pop("_project_root", None)
    config["paths"].update(
        {
            "output_grounding_dir": str(tmp_path / "grounding"),
            "output_profiles_dir": str(tmp_path / "profiles"),
            "feature_registry": str(tmp_path / "foundation" / "feature_registry.csv"),
            "approved_variables": str(tmp_path / "foundation" / "approved_variables.yaml"),
            "multimodal_master_table": str(tmp_path / "foundation" / "multimodal_master_table.csv"),
            "report_path": str(tmp_path / "reports" / "phase1_grounding_report.md"),
            "literature_registry_csv": str(tmp_path / "literature_registry.csv"),
            "literature_registry_jsonl": str(tmp_path / "literature_registry.jsonl"),
            "literature_deduplication_report": str(tmp_path / "literature_deduplication_report.csv"),
            "corpus_manifest": str(tmp_path / "corpus_manifest.json"),
        }
    )
    path = tmp_path / "grounding.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_grounding_functional_with_mock_online_api(monkeypatch, tmp_path):
    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fake_online_literature_search)
    run_foundation_pipeline(toy_foundation_config_path(tmp_path))
    result = run_grounding_pipeline(_tmp_config(tmp_path))
    required = [
        tmp_path / "grounding" / "evidence_table.csv",
        tmp_path / "grounding" / "evidence_table.json",
        tmp_path / "grounding" / "mechanism_graph_nodes.csv",
        tmp_path / "grounding" / "mechanism_graph_edges.csv",
        tmp_path / "grounding" / "mechanism_graph.json",
        tmp_path / "grounding" / "evidence_to_variable_map.yaml",
        tmp_path / "grounding" / "approved_variables_from_grounding.yaml",
        tmp_path / "profiles" / "theoretical_profile.yaml",
        tmp_path / "profiles" / "observed_profile.yaml",
        tmp_path / "profiles" / "analysis_ready_profile.yaml",
        tmp_path / "reports" / "phase1_grounding_report.md",
    ]
    for path in required:
        assert Path(path).exists(), path
    evidence = read_csv(tmp_path / "grounding" / "evidence_table.csv")
    assert evidence
    mapping = read_yaml(tmp_path / "grounding" / "evidence_to_variable_map.yaml")
    by_concept = {item["concept"]: set(item.get("approved_data_features", [])) for item in mapping["mappings"]}
    assert by_concept["slow-wave generation"] & {"slow_wave_density", "delta_power"}
    assert by_concept["thalamocortical coupling"] & {"thalamus_DMN_FC", "thalamic_radiation_FA"}
    assert by_concept["insomnia severity"] & {"ISI", "PSQI"}
    unavailable = [item for item in mapping["mappings"] if item["mapping_status"] == "unavailable"]
    assert all(not item.get("approved_data_features") for item in unavailable)
    ready = read_yaml(tmp_path / "profiles" / "analysis_ready_profile.yaml")
    registry_vars = {row["feature_name"] for row in read_csv(tmp_path / "foundation" / "feature_registry.csv")}
    assert {item["feature_name"] for item in ready["features"]} <= registry_vars
    assert result["api_summary"]["enabled"] is True
