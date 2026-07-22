from __future__ import annotations

from pathlib import Path


def test_hypothesis_experiment_script_logs_input_paths():
    script = Path("scripts/test_hypothesis_experiment.sh").read_text(encoding="utf-8")

    assert "logs/test_hypothesis_experiment_" in script
    assert "exec > >(tee -a \"$LOG_FILE\") 2>&1" in script
    assert '"hypothesis_input"' in script
    assert '"experiment_input"' in script
    for field in (
        "evidence_table_json",
        "knowledge_graph_json",
        "prior_hypotheses_json",
        "hypothesis_pool",
        "data_profile",
        "approved_variables",
        "variable_mapping",
    ):
        assert field in script
