import json
from pathlib import Path

from sleep_ai_scientist.common.io import read_json, read_yaml, write_json, write_yaml
from sleep_ai_scientist.discovery_loop.discovery_runner import _build_grounding_retrieval_query_profile, _collect_iteration_metrics, run_discovery_loop


def test_grounding_retrieval_query_profile_combines_research_intent_gaps_and_data_features(tmp_path):
    hypothesis_config = tmp_path / "hypothesis_config.yaml"
    foundation_config = tmp_path / "foundation_update_config.yaml"
    foundation_dir = tmp_path / "foundation"
    foundation_dir.mkdir()
    feature_registry = foundation_dir / "feature_registry.csv"
    approved_variables = foundation_dir / "approved_variables.yaml"
    write_yaml(hypothesis_config, {"hypothesis": {"research_question": "sleep neuroimaging mechanisms and measurable multimodal biomarkers"}})
    feature_registry.write_text(
        "feature_name,modality,approved\nthalamus_DMN_FC,fMRI,true\nmean_FD,fMRI,true\nunapproved_noise,fMRI,false\n",
        encoding="utf-8",
    )
    write_yaml(approved_variables, {"fMRI": ["thalamus_DMN_FC"], "qc": ["mean_FD"]})
    write_yaml(
        foundation_config,
        {"outputs": {"feature_registry": str(feature_registry), "approved_variables": str(approved_variables)}},
    )
    literature_expansion = {
        "accepted_queries": [
            {
                "query": "thalamus default mode network salience network functional connectivity sleep fMRI",
                "intent_type": "resolve_failed_test",
                "rationale": "primary test failed for thalamus_DMN_FC -> insomnia severity",
            }
        ],
        "signals": {"failed_tests": 1, "missing_variables": 2},
    }

    profile = _build_grounding_retrieval_query_profile(
        literature_expansion,
        hypothesis_config_path=hypothesis_config,
        foundation_update={"foundation_config": str(foundation_config)},
    )

    query = profile["query"]
    assert "sleep neuroimaging mechanisms" in query
    assert "thalamus default mode network" in query
    assert "primary test failed" in query
    assert "thalamus DMN FC" in query
    assert "mean FD" in query
    assert "unapproved_noise" not in query
    assert profile["sources"]["research_question"] == ["sleep neuroimaging mechanisms and measurable multimodal biomarkers"]
    assert profile["sources"]["accepted_queries"] == ["thalamus default mode network salience network functional connectivity sleep fMRI"]


def test_discovery_loop_runs_iterations_and_snapshots(monkeypatch, tmp_path):
    hypothesis_dir = tmp_path / "hypotheses"
    experiment_dir = tmp_path / "experiments"
    reports_dir = tmp_path / "reports"
    feature_root = tmp_path / "features"
    feedback_path = hypothesis_dir / "experimental_feedback.json"
    reward_memory = tmp_path / "reward_memory.json"
    hypothesis_report = reports_dir / "hypothesis_report.md"
    experiment_report = reports_dir / "experiment_report.md"
    experiment_results = experiment_dir / "experiment_results.json"
    visualization_dir = experiment_dir / "visuals"

    hypothesis_config = tmp_path / "hypothesis_config.yaml"
    experiment_config = tmp_path / "experiment_config.yaml"
    loop_config = tmp_path / "discovery_loop_config.yaml"

    write_yaml(
        hypothesis_config,
        {
            "paths": {
                "output_hypotheses_dir": str(hypothesis_dir),
                "experimental_feedback": str(feedback_path),
                "reward_memory": str(reward_memory),
                "report_path": str(hypothesis_report),
            }
        },
    )
    write_yaml(
        experiment_config,
        {
            "feature_extraction": {"output_root": str(feature_root)},
            "paths": {
                "experiment_output_dir": str(experiment_dir),
                "experiment_results": str(experiment_results),
                "experimental_feedback": str(feedback_path),
                "experiment_report": str(experiment_report),
            },
        },
    )
    write_yaml(
        loop_config,
        {
            "discovery_loop": {
                "run_id": "test_loop",
                "max_iterations": 2,
                "verbose": False,
                "snapshot_features": True,
                "stop_conditions": {
                    "no_active_hypotheses": True,
                    "no_experimental_feedback": False,
                    "reward_convergence": {"enabled": False},
                },
            },
            "hypothesis": {"config_path": str(hypothesis_config)},
            "experiment": {"config_path": str(experiment_config)},
            "paths": {
                "loop_output_dir": str(tmp_path / "loop"),
                "iteration_state": str(tmp_path / "loop" / "loop_state.json"),
                "iteration_report": str(reports_dir / "phase4_discovery_loop_report.md"),
            },
        },
    )

    calls = {"hypothesis": 0, "experiment": 0}

    def fake_hypothesis_pipeline(config_path):
        calls["hypothesis"] += 1
        hypothesis_id = f"hyp-{calls['hypothesis']}"
        write_json(
            hypothesis_dir / "hypothesis_pool.json",
            [
                {
                    "hypothesis_id": hypothesis_id,
                    "title": f"Hypothesis {calls['hypothesis']}",
                    "status": "active",
                    "elo_rating": 1300 + calls["hypothesis"],
                }
            ],
        )
        write_json(hypothesis_dir / "top_k_hypotheses.json", [{"hypothesis_id": hypothesis_id, "status": "active"}])
        hypothesis_report.parent.mkdir(parents=True, exist_ok=True)
        hypothesis_report.write_text("hypothesis report", encoding="utf-8")
        return {"hypotheses": 1, "active": 1}

    def fake_experiment_pipeline(config_path):
        calls["experiment"] += 1
        write_json(experiment_results, [{"plan_id": f"plan-{calls['experiment']}"}])
        write_json(
            feedback_path,
            [
                {
                    "feedback_id": f"fb-{calls['experiment']}",
                    "hypothesis_id": f"hyp-{calls['experiment']}",
                    "computed_reward": 0.5,
                }
            ],
        )
        experiment_report.parent.mkdir(parents=True, exist_ok=True)
        experiment_report.write_text("experiment report", encoding="utf-8")
        visualization_dir.mkdir(parents=True, exist_ok=True)
        (visualization_dir / "index.html").write_text("<html></html>", encoding="utf-8")
        write_json(visualization_dir / "visualization_manifest.json", {"html": str(visualization_dir / "index.html")})
        (feature_root / "fmri" / f"plan-{calls['experiment']}").mkdir(parents=True, exist_ok=True)
        return {"plans": 1, "results": str(experiment_results), "visualizations": {"html": str(visualization_dir / "index.html")}}

    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_hypothesis_pipeline", fake_hypothesis_pipeline)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_experiment_pipeline", fake_experiment_pipeline)

    summary = run_discovery_loop(loop_config)

    assert summary["iterations"] == 2
    assert summary["stop_reason"] == "max_iterations"
    assert calls == {"hypothesis": 2, "experiment": 2}
    assert (tmp_path / "loop" / "iteration_001" / "hypothesis" / "hypothesis_pool.json").exists()
    assert (tmp_path / "loop" / "iteration_002" / "experiment" / "experiment_results.json").exists()
    assert (tmp_path / "loop" / "iteration_002" / "experiment" / "visuals" / "index.html").exists()
    assert (tmp_path / "loop" / "iteration_002" / "features" / "fmri").exists()
    state = read_json(tmp_path / "loop" / "loop_state.json")
    assert len(state["iterations"]) == 2
    assert state["iterations"][0]["hypothesis_feedback_input"]["available"] is False
    assert state["iterations"][1]["hypothesis_feedback_input"]["available"] is True
    assert state["result"]["grounding_refreshes"] == 0
    assert all(item["foundation_update"]["reason"] == "foundation_grounding_refresh_disabled" for item in state["iterations"])
    assert (reports_dir / "phase4_discovery_loop_report.md").exists()


def test_discovery_loop_updates_foundation_and_refreshes_grounding_after_experiment_features(monkeypatch, tmp_path):
    hypothesis_dir = tmp_path / "hypotheses"
    experiment_dir = tmp_path / "experiments"
    foundation_dir = tmp_path / "foundation"
    grounding_dir = tmp_path / "grounding"
    profiles_dir = tmp_path / "profiles"
    feedback_path = hypothesis_dir / "experimental_feedback.json"
    feature_table = tmp_path / "features" / "fmri" / "plan-1" / "fmri_features.csv"
    feature_table.parent.mkdir(parents=True, exist_ok=True)
    feature_table.write_text("subject_id,group,thalamus_DMN_FC,mean_FD\nS001,INS,0.2,0.1\nS002,HC,0.1,0.08\n", encoding="utf-8")

    hypothesis_config = tmp_path / "hypothesis_config.yaml"
    experiment_config = tmp_path / "experiment_config.yaml"
    foundation_config = tmp_path / "foundation_config.yaml"
    grounding_config = tmp_path / "grounding_config.yaml"
    loop_config = tmp_path / "discovery_loop_config.yaml"

    write_yaml(hypothesis_config, {"paths": {"output_hypotheses_dir": str(hypothesis_dir), "experimental_feedback": str(feedback_path)}})
    write_yaml(
        experiment_config,
        {
            "feature_extraction": {"output_root": str(tmp_path / "features")},
            "paths": {
                "experiment_output_dir": str(experiment_dir),
                "experiment_results": str(experiment_dir / "experiment_results.json"),
                "experimental_feedback": str(feedback_path),
            },
        },
    )
    write_yaml(
        foundation_config,
        {
            "foundation": {"mode": "empty_foundation"},
            "runtime": {"allow_fixtures": False},
            "paths": {"foundation_dir": str(foundation_dir), "reports_dir": str(tmp_path / "reports")},
            "inputs": {},
            "outputs": {
                "subject_index": str(foundation_dir / "subject_index.csv"),
                "feature_registry": str(foundation_dir / "feature_registry.csv"),
                "approved_variables": str(foundation_dir / "approved_variables.yaml"),
                "data_dictionary": str(foundation_dir / "data_dictionary.yaml"),
                "qc_summary": str(foundation_dir / "qc_summary.csv"),
                "multimodal_master_table": str(foundation_dir / "multimodal_master_table.csv"),
                "manifest": str(foundation_dir / "foundation_manifest.json"),
                "data_asset_registry": str(foundation_dir / "data_asset_registry.jsonl"),
                "update_history": str(foundation_dir / "foundation_update_history.jsonl"),
                "report": str(tmp_path / "reports" / "phase0_foundation_report.md"),
            },
            "subject_id": {"column": "subject_id", "aliases": []},
            "modalities": ["fMRI"],
            "qc": {"pass_values": ["pass"], "caution_values": [], "fail_values": ["fail"]},
            "thresholds": {"max_missing_rate_primary": 1.0, "max_missing_rate_secondary": 1.0, "min_n_total": 1, "min_n_per_group": 0},
        },
    )
    write_yaml(
        grounding_config,
        {
            "runtime": {"allow_fixtures": False},
            "paths": {
                "feature_registry": str(foundation_dir / "feature_registry.csv"),
                "approved_variables": str(foundation_dir / "approved_variables.yaml"),
                "multimodal_master_table": str(foundation_dir / "multimodal_master_table.csv"),
                "output_grounding_dir": str(grounding_dir),
                "output_profiles_dir": str(profiles_dir),
            },
            "api": {"enabled": False},
        },
    )
    write_yaml(
        loop_config,
        {
            "discovery_loop": {"run_id": "refresh_loop", "max_iterations": 1, "verbose": False, "snapshot_features": False, "enable_foundation_grounding_refresh": True, "stop_conditions": {"reward_convergence": {"enabled": False}, "no_active_hypotheses": False}},
            "foundation": {"config_path": str(foundation_config)},
            "literature": {"enabled": True, "intent_llm_enabled": False, "config_path": "configs/literature_library_config.yaml", "query_config_path": "configs/literature_queries.yaml", "library_version": "test_library"},
            "grounding": {"config_path": str(grounding_config), "corpus_version": "test_data_constrained"},
            "hypothesis": {"config_path": str(hypothesis_config)},
            "experiment": {"config_path": str(experiment_config)},
            "paths": {"loop_output_dir": str(tmp_path / "loop"), "iteration_state": str(tmp_path / "loop" / "loop_state.json"), "iteration_report": str(tmp_path / "reports" / "loop.md")},
        },
    )

    def fake_hypothesis_pipeline(config_path):
        write_json(hypothesis_dir / "hypothesis_pool.json", [{"hypothesis_id": "h1", "status": "active"}])
        write_json(hypothesis_dir / "top_k_hypotheses.json", [{"hypothesis_id": "h1"}])
        return {"hypotheses": 1}

    def fake_experiment_pipeline(config_path):
        write_json(experiment_dir / "experiment_results.json", [{"plan_id": "plan-1"}])
        write_json(feedback_path, [{"hypothesis_id": "h1", "computed_reward": 0.4}])
        return {"plans": 1, "feature_tables": [{"modality": "fMRI", "path": str(feature_table)}], "experimental_feedback": str(feedback_path)}

    grounding_calls = []
    literature_calls = []

    def fake_literature_build(config_path, query_config_path="configs/literature_queries.yaml", library_version=None, **kwargs):
        literature_calls.append({"config_path": str(config_path), "query_config_path": str(query_config_path), "library_version": library_version})
        return {"registry_records": 3, "rag_index": {"chunk_count": 2, "embedding": {"vector_count": 2}}}

    def fake_grounding_pipeline(config_path, query_config_path=None, corpus_version="", retrieval_query=None):
        grounding_calls.append({"config_path": str(config_path), "corpus_version": corpus_version, "retrieval_query": retrieval_query})
        write_json(grounding_dir / "mechanism_graph.json", {"nodes": [], "edges": []})
        return {"evidence": 1, "graph_nodes": 1}

    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_hypothesis_pipeline", fake_hypothesis_pipeline)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_experiment_pipeline", fake_experiment_pipeline)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_literature_build", fake_literature_build)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_grounding_pipeline", fake_grounding_pipeline)

    summary = run_discovery_loop(loop_config)
    state = read_json(tmp_path / "loop" / "loop_state.json")

    assert summary["grounding_refreshes"] == 1
    assert literature_calls == []
    assert grounding_calls == [{"config_path": str(grounding_config), "corpus_version": "test_data_constrained", "retrieval_query": "thalamus DMN FC mean FD group"}]
    assert state["iterations"][0]["literature_expansion"]["accepted_query_count"] == 0
    assert state["iterations"][0]["literature_refresh"]["refreshed"] is False
    assert state["iterations"][0]["literature_refresh"]["reason"] == "no_new_experiment_queries"
    assert state["iterations"][0]["foundation_update"]["foundation_changed"] is True
    assert "thalamus_DMN_FC" in (foundation_dir / "feature_registry.csv").read_text(encoding="utf-8")
    assert state["iterations"][0]["foundation_update"]["data_asset_registry"] == str(foundation_dir / "data_asset_registry.jsonl")
    assert state["iterations"][0]["foundation_update"]["update_history"] == str(foundation_dir / "foundation_update_history.jsonl")
    asset_records = [
        json.loads(line)
        for line in (foundation_dir / "data_asset_registry.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert asset_records[0]["source"] == "experiment"
    assert asset_records[0]["modality"] == "fMRI"
    assert asset_records[0]["row_count"] == 2
    assert asset_records[0]["column_count"] == 4
    assert asset_records[0]["columns"] == ["subject_id", "group", "thalamus_DMN_FC", "mean_FD"]
    assert asset_records[0]["iteration_id"] == "iteration_001"
    update_events = [
        json.loads(line)
        for line in (foundation_dir / "foundation_update_history.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert update_events[0]["source"] == "experiment"
    assert update_events[0]["asset_count"] == 1
    assert update_events[0]["foundation_manifest"] == str(foundation_dir / "foundation_manifest.json")
    manifest = read_json(foundation_dir / "foundation_manifest.json")
    assert manifest["data_assets"]["registry"] == str(foundation_dir / "data_asset_registry.jsonl")
    assert manifest["data_assets"]["update_history"] == str(foundation_dir / "foundation_update_history.jsonl")
    assert state["result"]["last_experiment_feedback"] == str(feedback_path)


def test_discovery_loop_refreshes_literature_only_when_experiment_intent_accepts_queries(monkeypatch, tmp_path):
    hypothesis_dir = tmp_path / "hypotheses"
    experiment_dir = tmp_path / "experiments"
    foundation_dir = tmp_path / "foundation"
    grounding_dir = tmp_path / "grounding"
    feedback_path = hypothesis_dir / "experimental_feedback.json"
    feature_table = tmp_path / "features" / "fmri" / "plan-1" / "fmri_features.csv"
    feature_table.parent.mkdir(parents=True, exist_ok=True)
    feature_table.write_text("subject_id,thalamus_DMN_FC\nS001,0.2\nS002,0.1\n", encoding="utf-8")
    query_config = tmp_path / "literature_queries.yaml"
    write_yaml(
        query_config,
        {
            "query_sets": {
                "library": {
                    "settings": {"providers": ["pubmed"]},
                    "queries": {"human_sleep_neuroimaging": ["sleep thalamus connectivity fMRI"]},
                }
            }
        },
    )

    hypothesis_config = tmp_path / "hypothesis_config.yaml"
    experiment_config = tmp_path / "experiment_config.yaml"
    foundation_config = tmp_path / "foundation_config.yaml"
    grounding_config = tmp_path / "grounding_config.yaml"
    loop_config = tmp_path / "discovery_loop_config.yaml"

    write_yaml(hypothesis_config, {"paths": {"output_hypotheses_dir": str(hypothesis_dir), "experimental_feedback": str(feedback_path)}})
    write_yaml(
        experiment_config,
        {"paths": {"experiment_results": str(experiment_dir / "experiment_results.json"), "experimental_feedback": str(feedback_path)}},
    )
    write_yaml(
        foundation_config,
        {
            "runtime": {"allow_fixtures": False},
            "paths": {"foundation_dir": str(foundation_dir)},
            "inputs": {},
            "outputs": {
                "subject_index": str(foundation_dir / "subject_index.csv"),
                "feature_registry": str(foundation_dir / "feature_registry.csv"),
                "approved_variables": str(foundation_dir / "approved_variables.yaml"),
                "data_dictionary": str(foundation_dir / "data_dictionary.yaml"),
                "qc_summary": str(foundation_dir / "qc_summary.csv"),
                "multimodal_master_table": str(foundation_dir / "multimodal_master_table.csv"),
                "manifest": str(foundation_dir / "foundation_manifest.json"),
                "data_asset_registry": str(foundation_dir / "data_asset_registry.jsonl"),
                "update_history": str(foundation_dir / "foundation_update_history.jsonl"),
                "report": str(tmp_path / "reports" / "phase0_foundation_report.md"),
            },
            "subject_id": {"column": "subject_id", "aliases": []},
            "modalities": ["fMRI"],
            "qc": {"pass_values": ["pass"], "caution_values": [], "fail_values": ["fail"]},
            "thresholds": {"max_missing_rate_primary": 1.0, "max_missing_rate_secondary": 1.0, "min_n_total": 1, "min_n_per_group": 0},
        },
    )
    write_yaml(grounding_config, {"paths": {"output_grounding_dir": str(grounding_dir)}})
    write_yaml(
        loop_config,
        {
            "discovery_loop": {"max_iterations": 1, "verbose": False, "snapshot_features": False, "enable_foundation_grounding_refresh": True, "stop_conditions": {"reward_convergence": {"enabled": False}, "no_active_hypotheses": False}},
            "foundation": {"config_path": str(foundation_config)},
            "literature": {
                "enabled": True,
                "intent_llm_enabled": False,
                "intent_log_path": str(tmp_path / "query_expansion_intents.jsonl"),
                "config_path": "configs/literature_library_config.yaml",
                "query_config_path": str(query_config),
                "library_version": "test_library",
            },
            "grounding": {"config_path": str(grounding_config), "corpus_version": "test_data_constrained"},
            "hypothesis": {"config_path": str(hypothesis_config)},
            "experiment": {"config_path": str(experiment_config)},
            "paths": {"loop_output_dir": str(tmp_path / "loop"), "iteration_state": str(tmp_path / "loop" / "loop_state.json"), "iteration_report": str(tmp_path / "reports" / "loop.md")},
        },
    )

    def fake_hypothesis_pipeline(config_path):
        write_json(hypothesis_dir / "hypothesis_pool.json", [{"hypothesis_id": "h1", "status": "active"}])
        write_json(hypothesis_dir / "top_k_hypotheses.json", [{"hypothesis_id": "h1"}])
        return {"hypotheses": 1}

    def fake_experiment_pipeline(config_path):
        write_json(experiment_dir / "experiment_results.json", [{"plan_id": "plan-1"}])
        write_json(feedback_path, [{"hypothesis_id": "h1", "computed_reward": 0.8}])
        return {"plans": 1, "feature_tables": [{"modality": "fMRI", "path": str(feature_table)}], "experimental_feedback": str(feedback_path)}

    literature_calls = []
    append_calls = []

    def fake_build_intent(experiment_summary, iteration_id, query_config_path, **kwargs):
        return {
            "iteration_id": iteration_id,
            "accepted_query_count": 1,
            "accepted_queries": [
                {
                    "query": "thalamus default mode network salience network functional connectivity sleep fMRI",
                    "intent_type": "resolve_failed_test",
                    "source_iteration": iteration_id,
                }
            ],
            "candidate_count": 1,
            "rejected_duplicate_count": 0,
            "rejected_invalid_count": 0,
            "signals": {"failed_tests": 1, "negative_control_failures": 0, "missing_variables": 0, "modality_gaps": 0},
        }

    def fake_append(query_config_path, accepted_queries):
        append_calls.append({"query_config_path": str(query_config_path), "queries": accepted_queries})
        return {"appended": len(accepted_queries), "group": "experiment_feedback_expansion", "query_config": str(query_config_path)}

    def fake_literature_build(config_path, query_config_path="configs/literature_queries.yaml", library_version=None, **kwargs):
        literature_calls.append({"query_config_path": str(query_config_path), "library_version": library_version, "kwargs": kwargs})
        return {"registry_records": 5, "rag_index": {"chunk_count": 4, "embedding": {"vector_count": 4}}}

    grounding_calls = []

    def fake_grounding_pipeline(config_path, query_config_path=None, corpus_version="", retrieval_query=None):
        grounding_calls.append({"retrieval_query": retrieval_query, "corpus_version": corpus_version})
        return {"evidence": 1, "graph_nodes": 1}

    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_hypothesis_pipeline", fake_hypothesis_pipeline)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_experiment_pipeline", fake_experiment_pipeline)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.build_literature_expansion_plan", fake_build_intent)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.append_queries_to_config", fake_append)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_literature_build", fake_literature_build)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_grounding_pipeline", fake_grounding_pipeline)

    run_discovery_loop(loop_config)
    state = read_json(tmp_path / "loop" / "loop_state.json")

    assert append_calls[0]["query_config_path"] == str(query_config.resolve())
    assert len(literature_calls) == 1
    incremental_config = Path(literature_calls[0]["query_config_path"])
    assert incremental_config.name == "literature_incremental_queries.yaml"
    incremental_payload = read_yaml(incremental_config)
    assert incremental_payload["query_sets"]["library"]["queries"] == {
        "experiment_feedback_expansion": [
            "thalamus default mode network salience network functional connectivity sleep fMRI"
        ]
    }
    assert state["iterations"][0]["literature_expansion"]["accepted_query_count"] == 1
    assert state["iterations"][0]["literature_expansion"]["incremental_query_config"] == str(incremental_config)
    assert state["iterations"][0]["literature_refresh"]["refreshed"] is True
    assert "thalamus default mode network salience network functional connectivity sleep fMRI" in grounding_calls[0]["retrieval_query"]
    assert "resolve failed test" in grounding_calls[0]["retrieval_query"]
    assert "thalamus DMN FC" in grounding_calls[0]["retrieval_query"]


def test_discovery_loop_builds_literature_intent_when_foundation_is_unchanged(monkeypatch, tmp_path):
    hypothesis_dir = tmp_path / "hypotheses"
    experiment_dir = tmp_path / "experiments"
    feedback_path = hypothesis_dir / "experimental_feedback.json"
    query_config = tmp_path / "literature_queries.yaml"
    loop_config = tmp_path / "discovery_loop_config.yaml"
    hypothesis_config = tmp_path / "hypothesis_config.yaml"
    experiment_config = tmp_path / "experiment_config.yaml"
    foundation_config = tmp_path / "foundation_config.yaml"
    grounding_config = tmp_path / "grounding_config.yaml"

    write_yaml(
        query_config,
        {
            "query_sets": {"library": {"queries": {"core": ["insomnia EEG"]}}},
            "settings": {"max_results_per_query": 1, "providers": []},
        },
    )
    write_yaml(hypothesis_config, {"paths": {"output_hypotheses_dir": str(hypothesis_dir), "experimental_feedback": str(feedback_path)}})
    write_yaml(
        experiment_config,
        {
            "paths": {
                "experiment_output_dir": str(experiment_dir),
                "experiment_results": str(experiment_dir / "experiment_results.json"),
                "experimental_feedback": str(feedback_path),
            }
        },
    )
    write_yaml(foundation_config, {"paths": {}})
    write_yaml(grounding_config, {"paths": {}})
    write_yaml(
        loop_config,
        {
            "discovery_loop": {"max_iterations": 1, "verbose": False, "snapshot_features": False, "enable_foundation_grounding_refresh": True, "stop_conditions": {"reward_convergence": {"enabled": False}, "no_active_hypotheses": False}},
            "foundation": {"config_path": str(foundation_config)},
            "literature": {
                "enabled": True,
                "intent_llm_enabled": False,
                "intent_log_path": str(tmp_path / "query_expansion_intents.jsonl"),
                "config_path": "configs/literature_library_config.yaml",
                "query_config_path": str(query_config),
                "library_version": "test_library",
            },
            "grounding": {"config_path": str(grounding_config), "corpus_version": "test_data_constrained"},
            "hypothesis": {"config_path": str(hypothesis_config)},
            "experiment": {"config_path": str(experiment_config)},
            "paths": {"loop_output_dir": str(tmp_path / "loop"), "iteration_state": str(tmp_path / "loop" / "loop_state.json"), "iteration_report": str(tmp_path / "reports" / "loop.md")},
        },
    )

    def fake_hypothesis_pipeline(config_path):
        write_json(hypothesis_dir / "hypothesis_pool.json", [{"hypothesis_id": "h1", "status": "active"}])
        write_json(hypothesis_dir / "top_k_hypotheses.json", [{"hypothesis_id": "h1"}])
        return {"hypotheses": 1}

    def fake_experiment_pipeline(config_path):
        write_json(experiment_dir / "experiment_results.json", [{"plan_id": "plan-1"}])
        write_json(feedback_path, [{"hypothesis_id": "h1", "computed_reward": 0.2}])
        return {"plans": 1, "experimental_feedback": str(feedback_path)}

    literature_calls = []

    def fake_build_intent(experiment_summary, iteration_id, query_config_path, **kwargs):
        return {
            "iteration_id": iteration_id,
            "accepted_query_count": 1,
            "accepted_queries": [{"query": "failed insomnia hypothesis sleep spindle EEG", "intent_type": "resolve_failed_test", "source_iteration": iteration_id}],
            "candidate_count": 1,
            "rejected_duplicate_count": 0,
            "rejected_invalid_count": 0,
            "signals": {"failed_tests": 1},
        }

    def fake_literature_build(config_path, query_config_path="configs/literature_queries.yaml", library_version=None, **kwargs):
        literature_calls.append({"query_config_path": str(query_config_path), "library_version": library_version})
        return {"registry_records": 2, "rag_index": {"chunk_count": 1, "embedding": {"vector_count": 1}}}

    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_hypothesis_pipeline", fake_hypothesis_pipeline)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_experiment_pipeline", fake_experiment_pipeline)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner._update_foundation_from_experiment_features", lambda *args, **kwargs: {"foundation_changed": False, "reason": "no_new_features"})
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.build_literature_expansion_plan", fake_build_intent)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_literature_build", fake_literature_build)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_grounding_pipeline", lambda *args, **kwargs: {"evidence": 1})

    run_discovery_loop(loop_config)
    state = read_json(tmp_path / "loop" / "loop_state.json")

    assert len(literature_calls) == 1
    assert state["iterations"][0]["foundation_update"]["foundation_changed"] is False
    assert state["iterations"][0]["literature_expansion"]["accepted_query_count"] == 1
    assert state["iterations"][0]["literature_refresh"]["refreshed"] is True


def test_discovery_loop_next_hypothesis_reads_previous_experiment_feedback(monkeypatch, tmp_path):
    hypothesis_dir = tmp_path / "hypotheses"
    experiment_dir = tmp_path / "experiments"
    feedback_path = hypothesis_dir / "experimental_feedback.json"
    hypothesis_config = tmp_path / "hypothesis_config.yaml"
    experiment_config = tmp_path / "experiment_config.yaml"
    loop_config = tmp_path / "discovery_loop_config.yaml"

    write_yaml(hypothesis_config, {"paths": {"output_hypotheses_dir": str(hypothesis_dir), "experimental_feedback": str(feedback_path)}})
    write_yaml(experiment_config, {"paths": {"experiment_results": str(experiment_dir / "experiment_results.json"), "experimental_feedback": str(feedback_path)}})
    write_yaml(
        loop_config,
        {
            "discovery_loop": {"max_iterations": 2, "verbose": False, "snapshot_features": False, "stop_conditions": {"reward_convergence": {"enabled": False}, "no_active_hypotheses": False}},
            "hypothesis": {"config_path": str(hypothesis_config)},
            "experiment": {"config_path": str(experiment_config)},
            "paths": {"loop_output_dir": str(tmp_path / "loop"), "iteration_state": str(tmp_path / "loop" / "loop_state.json"), "iteration_report": str(tmp_path / "reports" / "loop.md")},
        },
    )

    feedback_seen_by_hypothesis: list[bool] = []

    def fake_hypothesis_pipeline(config_path):
        feedback_seen_by_hypothesis.append(feedback_path.exists())
        iteration = len(feedback_seen_by_hypothesis)
        write_json(hypothesis_dir / "hypothesis_pool.json", [{"hypothesis_id": f"h{iteration}", "status": "active"}])
        write_json(hypothesis_dir / "top_k_hypotheses.json", [{"hypothesis_id": f"h{iteration}"}])
        return {"hypotheses": 1, "feedback_seen": feedback_path.exists()}

    def fake_experiment_pipeline(config_path):
        experiment_dir.mkdir(parents=True, exist_ok=True)
        write_json(experiment_dir / "experiment_results.json", [{"plan_id": "p"}])
        write_json(feedback_path, [{"hypothesis_id": "h", "computed_reward": 0.5}])
        return {"plans": 1, "experimental_feedback": str(feedback_path)}

    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_hypothesis_pipeline", fake_hypothesis_pipeline)
    monkeypatch.setattr("sleep_ai_scientist.discovery_loop.discovery_runner.run_experiment_pipeline", fake_experiment_pipeline)

    run_discovery_loop(loop_config)

    assert feedback_seen_by_hypothesis == [False, True]
    state = read_json(tmp_path / "loop" / "loop_state.json")
    assert state["iterations"][1]["hypothesis_feedback_input"]["available"] is True
    assert state["result"]["hypothesis_feedback_available"] is True


def test_discovery_loop_feedback_metrics_use_validated_flags(tmp_path):
    hypothesis_dir = tmp_path / "hypotheses"
    experiment_dir = tmp_path / "experiments"
    feedback_path = tmp_path / "feedback.json"
    hypothesis_config = tmp_path / "hypothesis_config.yaml"
    experiment_config = tmp_path / "experiment_config.yaml"
    write_json(hypothesis_dir / "hypothesis_pool.json", [{"hypothesis_id": "h1", "status": "active"}])
    write_json(hypothesis_dir / "top_k_hypotheses.json", [{"hypothesis_id": "h1", "status": "active"}])
    write_json(experiment_dir / "experiment_results.json", [{"plan_id": "p1"}])
    write_json(
        feedback_path,
        [
            {
                "hypothesis_id": "h1",
                "support": "inconclusive",
                "computed_reward": 0.325,
                "validated": False,
                "refuted": False,
            }
        ],
    )
    write_yaml(hypothesis_config, {"paths": {"output_hypotheses_dir": str(hypothesis_dir)}})
    write_yaml(
        experiment_config,
        {
            "paths": {
                "experiment_results": str(experiment_dir / "experiment_results.json"),
                "experimental_feedback": str(feedback_path),
            }
        },
    )

    metrics = _collect_iteration_metrics(
        iteration=1,
        hypothesis_config_path=hypothesis_config,
        experiment_config_path=experiment_config,
        previous_hypothesis_ids=set(),
    )

    assert metrics["reward_mean"] == 0.325
    assert metrics["validated_feedback"] == 0
    assert metrics["refuted_feedback"] == 0
