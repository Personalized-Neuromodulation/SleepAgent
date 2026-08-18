from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import config_path, load_config
from sleep_ai_scientist.common.io import read_json
from sleep_ai_scientist.hypothesis.agents.context_agent import ContextAgent
from sleep_ai_scientist.hypothesis.agents.evolution_memory_agent import EvolutionMemoryAgent
from sleep_ai_scientist.hypothesis.agents.generation_agent import GenerationAgent
from sleep_ai_scientist.hypothesis.agents.rank_agent import RankAgent
from sleep_ai_scientist.hypothesis.agents.review_agent import ReviewAgent
from sleep_ai_scientist.hypothesis.agents.state import HypothesisSessionState
from sleep_ai_scientist.hypothesis.agents.registry import HypothesisRegistry
from sleep_ai_scientist.llm.client import select_llm_profile
from sleep_ai_scientist.hypothesis.agents.memory import load_experimental_feedback, load_reward_memory
from sleep_ai_scientist.hypothesis.testability import load_analysis_ready_profile
from sleep_ai_scientist.experiment.design_constraints import build_experiment_design_constraints
from sleep_ai_scientist.schemas.evidence import EvidenceRecord
from sleep_ai_scientist.schemas.hypothesis import Hypothesis


class HypothesisSupervisor:
    """Five-agent hypothesis lifecycle orchestrator."""

    def __init__(self) -> None:
        self.context_agent = ContextAgent()
        self.generation_agent = GenerationAgent()
        self.review_agent = ReviewAgent()
        self.rank_agent = RankAgent()
        self.evolution_memory_agent = EvolutionMemoryAgent()

    def run(self, config_path_value: str | Path = "configs/hypothesis_config.yaml") -> dict[str, Any]:
        state = self.create_state(config_path_value)
        _log(state, f"start session={state.registry.session_id}")
        _log(
            state,
            f"inputs evidence={len(state.evidence_table)} graph_nodes={len(state.knowledge_graph.get('nodes', [])) if isinstance(state.knowledge_graph, dict) else 0} "
            f"graph_edges={len(state.knowledge_graph.get('edges', [])) if isinstance(state.knowledge_graph, dict) else 0} priors={len(state.prior_hypotheses)} "
            f"feedback={len(state.experimental_feedback)} memory={len(state.reward_memory)}",
        )
        _log(state, f"llm provider={state.config['_selected_llm'].get('provider')} model={state.config['_selected_llm'].get('model')} enabled={state.config['_selected_llm'].get('enabled')}")
        state = self.context_agent.run(state)
        _log(state, "ContextAgent done")
        state = self.generation_agent.run(state)
        _log(state, f"GenerationAgent done hypotheses={len(state.registry.all())}")
        state = self.review_agent.run(state)
        _log(state, f"ReviewAgent done active={len(state.registry.active())} reviews={len(state.registry.reviews)} duplicates_rejected={len(state.rejected_duplicates)}")
        state = self.rank_agent.run(state)
        _log(state, f"RankAgent done matches={len(state.registry.matches)}")
        state = self.evolution_memory_agent.run(state)
        _log(state, f"EvolutionMemoryAgent done feedback_updates={state.artifacts.get('feedback_updates', 0)} evolved={state.artifacts.get('evolved_hypothesis_id', '') or 'none'}")
        if state.artifacts.get("evolved_hypothesis_id"):
            state = self.review_agent.run(state)
            _log(state, f"ReviewAgent second pass done active={len(state.registry.active())} reviews={len(state.registry.reviews)}")
            state = self.rank_agent.run(state)
            _log(state, f"RankAgent second pass done matches={len(state.registry.matches)}")
        state = self.evolution_memory_agent.write_outputs(state)
        _log(state, f"outputs written dir={state.output_dir} report={state.report_path}")
        return _summary(state)

    def create_state(self, config_path_value: str | Path) -> HypothesisSessionState:
        config = _with_shared_llm_config(load_config(config_path_value))
        paths = dict(config.get("paths", {}))
        hypothesis_cfg = config.get("hypothesis", {})
        full_evidence_path = config_path(config, "evidence_table_json", "outputs/grounding/evidence_table.json")
        full_knowledge_graph_path = config_path(config, "knowledge_graph_json", "outputs/grounding/mechanism_graph.json")
        evidence_path = _preferred_existing_path(config, "llm_evidence_context_json", full_evidence_path)
        knowledge_graph_path = _preferred_existing_path(config, "llm_mechanism_context_json", full_knowledge_graph_path)
        prior_hypotheses_path = config_path(config, "prior_hypotheses_json", "outputs/hypotheses/top_k_hypotheses.json")
        analysis_ready_profile_path = config_path(config, "analysis_ready_profile", "outputs/profiles/analysis_ready_profile.yaml")
        output_dir = config_path(config, "output_hypotheses_dir", "outputs/hypotheses")
        report_path = config_path(config, "report_path", "reports/phase2_hypothesis_report.md")
        feedback_path = config_path(config, "experimental_feedback", "outputs/hypotheses/experimental_feedback.json")
        reward_memory_path = config_path(config, "reward_memory", "outputs/memory/reward_memory.json")
        evidence = _load_evidence_records(evidence_path)
        research_question = str(
            hypothesis_cfg.get("research_question")
            or hypothesis_cfg.get("research_goal")
            or " ".join(item.claim for item in evidence[:10])
        )
        session_id = str(hypothesis_cfg.get("session_id", "sleep_hypothesis_session"))
        config["_selected_llm"] = select_llm_config(config)
        config["_llm_tasks"] = {
            "hypothesis_generation": select_llm_profile(config, "hypothesis_generation", log_prefix="hypothesis"),
            "hypothesis_review": select_llm_profile(config, "hypothesis_review", log_prefix="hypothesis"),
            "hypothesis_rank": select_llm_profile(config, "hypothesis_rank", log_prefix="hypothesis"),
            "hypothesis_evolution": select_llm_profile(config, "hypothesis_evolution", log_prefix="hypothesis"),
            "hypothesis_meta_review": select_llm_profile(config, "hypothesis_meta_review", log_prefix="hypothesis"),
        }
        registry = HypothesisRegistry(session_id=session_id)
        state = HypothesisSessionState(
            config=config,
            research_question=research_question,
            evidence_table=evidence,
            knowledge_graph=_load_optional_json(knowledge_graph_path, {}),
            prior_hypotheses=_load_prior_hypotheses(prior_hypotheses_path),
            experimental_feedback=load_experimental_feedback(feedback_path),
            reward_memory=load_reward_memory(reward_memory_path),
            registry=registry,
            output_dir=output_dir,
            report_path=report_path,
        )
        state.artifacts["reward_memory_path"] = reward_memory_path
        state.artifacts["full_evidence_table_path"] = full_evidence_path
        state.artifacts["full_knowledge_graph_path"] = full_knowledge_graph_path
        state.artifacts["evidence_table_path"] = evidence_path
        state.artifacts["knowledge_graph_path"] = knowledge_graph_path
        state.artifacts["analysis_ready_profile_path"] = analysis_ready_profile_path
        state.artifacts["analysis_ready_profile"] = load_analysis_ready_profile(analysis_ready_profile_path)
        state.artifacts["experiment_design_constraints"] = build_experiment_design_constraints(
            previous_result_paths=_path_list(paths.get("previous_experiment_results")),
            previous_feedback_paths=_path_list(paths.get("previous_experimental_feedback")),
        )
        constraints = state.artifacts["experiment_design_constraints"]
        _log(
            state,
            "experiment_preflight_constraints "
            f"avoid_signatures={len(constraints.get('avoid_signatures', []))} "
            f"tested_hypotheses={len(constraints.get('tested_hypothesis_ids', []))} "
            f"failed_tests={len(constraints.get('failed_tests', []))} "
            f"negative_failed_predictors={len(constraints.get('negative_control_failed_predictors', []))}",
        )
        return state


def select_llm_config(config: dict[str, Any]) -> dict[str, Any]:
    config = _with_shared_llm_config(config)
    return select_llm_profile(config, "hypothesis_generation", log_prefix="hypothesis")


def _with_shared_llm_config(config: dict[str, Any]) -> dict[str, Any]:
    try:
        llm_config_path = config_path(config, "llm_config")
    except KeyError:
        return config
    if not llm_config_path.exists():
        return config
    shared = load_config(llm_config_path)
    shared.pop("_config_path", None)
    shared.pop("_project_root", None)
    merged = dict(config)
    for key in ("llm_provider", "online_llm", "ollama", "llm_profiles", "llm_tasks"):
        if key in shared:
            merged[key] = shared[key]
    return merged


def _load_evidence_records(path: Path) -> list[EvidenceRecord]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return [EvidenceRecord(**row) for row in read_json(path)]


def _preferred_existing_path(config: dict[str, Any], preferred_key: str, fallback: Path) -> Path:
    try:
        preferred = config_path(config, preferred_key)
    except KeyError:
        return fallback
    if preferred.exists() and preferred.stat().st_size > 0:
        return preferred
    return fallback


def _load_optional_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    return read_json(path)


def _load_prior_hypotheses(path: Path) -> list[Hypothesis]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows = read_json(path)
    if isinstance(rows, dict):
        rows = rows.get("hypotheses", [])
    return [Hypothesis(**row) for row in rows if isinstance(row, dict)]


def _path_list(value: Any) -> list[Path]:
    if value is None:
        return []
    if isinstance(value, (str, Path)):
        return [Path(value)]
    if isinstance(value, list):
        return [Path(item) for item in value if str(item)]
    return []


def _log(state: HypothesisSessionState, message: str) -> None:
    if bool(state.config.get("logging", {}).get("progress", True)):
        print(f"[hypothesis] {message}", flush=True)


def _summary(state: HypothesisSessionState) -> dict[str, Any]:
    return {
        "evidence": len(state.evidence_table),
        "hypotheses": len(state.registry.all()),
        "active": len(state.registry.active()),
        "reviews": len(state.registry.reviews),
        "matches": len(state.registry.matches),
        "duplicates_rejected": len(state.rejected_duplicates),
        "feedback": len(state.experimental_feedback),
        "feedback_updates": int(state.artifacts.get("feedback_updates", 0)),
        "reward_memory": len(state.reward_memory),
        "priors": len(state.artifacts.get("retrieved_priors", [])),
        "agents": ["ContextAgent", "GenerationAgent", "ReviewAgent", "RankAgent", "EvolutionMemoryAgent"],
        "output_hypotheses_dir": str(state.output_dir),
        "report_path": str(state.report_path),
    }
