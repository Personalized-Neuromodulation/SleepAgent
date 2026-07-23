from pathlib import Path
import json

import yaml

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.common.io import read_csv, read_json, read_yaml
from sleep_ai_scientist.api.literature_client import apply_query_config
from sleep_ai_scientist.foundation.foundation_pipeline import run_foundation_pipeline
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline
from tests.api_test_utils import fake_online_literature_search
from tests.config_helpers import empty_foundation_config_path


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _online_grounding_config(tmp_path: Path) -> Path:
    config = load_config("configs/grounding_config.yaml")
    config.pop("_config_path", None)
    config.pop("_project_root", None)
    literature_config = load_config("configs/literature_library_config.yaml")
    literature_config.pop("_config_path", None)
    literature_config.pop("_project_root", None)
    literature_config.setdefault("embedding", {})["enabled"] = False
    literature_config_path = _write_yaml(tmp_path / "literature_library_config.yaml", literature_config)
    config.setdefault("api", {})["enabled"] = True
    config["paths"]["literature_library_config"] = str(literature_config_path)
    config["paths"].update(
        {
            "feature_registry": str(tmp_path / "foundation" / "feature_registry.csv"),
            "approved_variables": str(tmp_path / "foundation" / "approved_variables.yaml"),
            "multimodal_master_table": str(tmp_path / "foundation" / "multimodal_master_table.csv"),
            "output_grounding_dir": str(tmp_path / "grounding"),
            "output_profiles_dir": str(tmp_path / "profiles"),
            "report_path": str(tmp_path / "reports" / "phase1_grounding_report.md"),
            "literature_registry_csv": str(tmp_path / "literature" / "literature_registry.csv"),
            "literature_registry_jsonl": str(tmp_path / "literature" / "literature_registry.jsonl"),
            "literature_deduplication_report": str(tmp_path / "grounding" / "literature_deduplication_report.csv"),
            "corpus_manifest": str(tmp_path / "grounding" / "corpus_manifest.json"),
        }
    )
    return _write_yaml(tmp_path / "grounding_online.yaml", config)


def test_empty_foundation_writes_empty_declared_basis(tmp_path):
    result = run_foundation_pipeline(empty_foundation_config_path(tmp_path))

    assert result["mode"] == "empty_foundation"
    assert result["subject_count"] == 0
    assert result["feature_count"] == 0
    assert read_csv(tmp_path / "foundation" / "subject_index.csv") == []
    assert read_csv(tmp_path / "foundation" / "feature_registry.csv") == []
    assert read_yaml(tmp_path / "foundation" / "approved_variables.yaml")["fMRI"] == []

    manifest = read_json(tmp_path / "foundation" / "foundation_manifest.json")
    assert manifest["real_subject_data_available"] is False
    assert manifest["feature_values_available"] is False


def test_online_no_fixture_script_query_config_is_available():
    config = load_config("configs/grounding_config.yaml")
    config = apply_query_config(config, "configs/literature_queries.yaml")

    assert config["query_set"]["version"]
    assert config["query_set"]["scope"] == "library"
    assert config["api"]["search_queries"]
    assert config["api"]["max_results_per_query"] > 0


def test_grounding_without_real_features_builds_evidence_and_theoretical_graph(monkeypatch, tmp_path):
    run_foundation_pipeline(empty_foundation_config_path(tmp_path))
    monkeypatch.setattr("sleep_ai_scientist.grounding.grounding_pipeline.search_literature_apis", fake_online_literature_search)
    result = run_grounding_pipeline(_online_grounding_config(tmp_path))

    evidence = json.loads((tmp_path / "grounding" / "evidence_table.json").read_text(encoding="utf-8"))
    graph = json.loads((tmp_path / "grounding" / "mechanism_graph.json").read_text(encoding="utf-8"))
    mapping = read_yaml(tmp_path / "grounding" / "evidence_to_variable_map.yaml")
    analysis_ready = read_yaml(tmp_path / "profiles" / "analysis_ready_profile.yaml")

    assert result["evidence"] > 0
    assert evidence
    assert all(not item["paper_id"].startswith("toy") for item in evidence)
    assert analysis_ready["features"] == []
    assert all(item["mapping_status"] == "unavailable" for item in mapping["mappings"])
    assert all(node["node_type"] != "DataFeature" for node in graph["nodes"])
    assert result["graph_nodes"] > 0
    assert result["graph_edges"] > 0
