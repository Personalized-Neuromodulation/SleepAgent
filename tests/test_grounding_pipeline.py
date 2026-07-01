from pathlib import Path

import yaml

from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline


def _tmp_config(tmp_path: Path) -> Path:
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
        }
    )
    path = tmp_path / "grounding.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_grounding_pipeline_generates_outputs(tmp_path):
    result = run_grounding_pipeline(_tmp_config(tmp_path))
    assert result["evidence"] > 0
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
        tmp_path / "reports" / "grounding_report.md",
    ]
    for path in required:
        assert Path(path).exists()
