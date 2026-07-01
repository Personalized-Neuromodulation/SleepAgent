from pathlib import Path

from sleep_ai_scientist.common.io import read_csv, read_yaml
from sleep_ai_scientist.foundation.foundation_pipeline import run_foundation_pipeline
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline


def test_grounding_functional_without_api():
    run_foundation_pipeline("configs/foundation_config.yaml")
    result = run_grounding_pipeline("configs/grounding_config.yaml")
    required = [
        "outputs/grounding/evidence_table.csv",
        "outputs/grounding/evidence_table.json",
        "outputs/grounding/mechanism_graph_nodes.csv",
        "outputs/grounding/mechanism_graph_edges.csv",
        "outputs/grounding/mechanism_graph.json",
        "outputs/grounding/evidence_to_variable_map.yaml",
        "outputs/grounding/approved_variables_from_grounding.yaml",
        "outputs/profiles/theoretical_profile.yaml",
        "outputs/profiles/observed_profile.yaml",
        "outputs/profiles/analysis_ready_profile.yaml",
        "reports/grounding_report.md",
    ]
    for path in required:
        assert Path(path).exists(), path
    evidence = read_csv(Path("outputs/grounding/evidence_table.csv"))
    assert evidence
    mapping = read_yaml(Path("outputs/grounding/evidence_to_variable_map.yaml"))
    by_concept = {item["concept"]: set(item.get("approved_data_features", [])) for item in mapping["mappings"]}
    assert by_concept["slow-wave generation"] & {"slow_wave_density", "delta_power"}
    assert by_concept["thalamocortical coupling"] & {"thalamus_DMN_FC", "thalamic_radiation_FA"}
    assert by_concept["insomnia severity"] & {"ISI", "PSQI"}
    unavailable = [item for item in mapping["mappings"] if item["mapping_status"] == "unavailable"]
    assert all(not item.get("approved_data_features") for item in unavailable)
    ready = read_yaml(Path("outputs/profiles/analysis_ready_profile.yaml"))
    registry_vars = {row["feature_name"] for row in read_csv(Path("data/foundation/feature_registry.csv"))}
    assert {item["feature_name"] for item in ready["features"]} <= registry_vars
    assert result["api_summary"]["enabled"] is False

