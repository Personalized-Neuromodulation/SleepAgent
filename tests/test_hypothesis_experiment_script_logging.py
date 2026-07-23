from __future__ import annotations

from pathlib import Path


def test_discovery_loop_script_logs_input_paths_and_accepts_iterations():
    script = Path("scripts/run_discovery_loop.sh").read_text(encoding="utf-8")

    assert "logs/run_discovery_loop_" in script
    assert "exec > >(tee -a \"$LOG_FILE\") 2>&1" in script
    assert "python - \"$RUN_CONFIG_PATH\" <<'PY'" in script
    assert "python - <<'PY' \"$RUN_CONFIG_PATH\"" not in script
    assert "ITERATIONS=" in script
    assert "max_iterations" in script
    assert '"hypothesis_input"' in script
    assert '"experiment_input"' in script
    for field in (
        "evidence_table_json",
        "knowledge_graph_json",
        "llm_evidence_context_json",
        "llm_mechanism_context_json",
        "prior_hypotheses_json",
        "hypothesis_pool",
        "data_profile",
        "approved_variables",
        "variable_mapping",
    ):
        assert field in script
    assert "enable_foundation_grounding_refresh" not in script
    assert "run_foundation_grounding_online.sh" not in script


def test_run_all_tests_script_runs_full_foundation_to_data_constrained_loop():
    script = Path("scripts/run_all_tests.sh").read_text(encoding="utf-8")

    assert "run_foundation_grounding_online.sh" in script
    assert "enable_foundation_grounding_refresh" in script
    assert "foundation:" in script
    assert "grounding:" in script
    assert "run_discovery_loop.sh" in script


def test_foundation_grounding_script_exports_env_and_prints_api_preflight():
    script = Path("scripts/run_foundation_grounding_online.sh").read_text(encoding="utf-8")

    assert "set -a" in script
    assert "source .env" in script
    assert "API environment preflight" in script
    assert "NCBI_EMAIL" in script
    assert "SEMANTIC_SCHOLAR_API_KEY" in script
    assert "MISSING" in script


def test_foundation_grounding_script_saves_literature_db_build_start_marker():
    script = Path("scripts/run_foundation_grounding_online.sh").read_text(encoding="utf-8")

    assert "LITERATURE_DB_BUILD_LOG=\"logs/literature_db_build_start.log\"" in script
    assert "Build online sleep literature SQLite DB" in script
    assert "tee -a \"$LITERATURE_DB_BUILD_LOG\"" in script
    assert "data/literature/sleep_literature.db" in script


def test_redundant_hypothesis_experiment_scripts_are_removed():
    assert not Path("scripts/test_hypothesis_experiment.sh").exists()
    assert not Path("scripts/test_experiment.sh").exists()
