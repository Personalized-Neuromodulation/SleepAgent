from pathlib import Path

from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline


def test_grounding_pipeline_generates_phase1_outputs():
    result = run_grounding_pipeline("configs/grounding_config.yaml")
    assert result["evidence"] > 0
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
        "reports/phase1_grounding_report.md",
    ]
    for path in required:
        assert Path(path).exists()
