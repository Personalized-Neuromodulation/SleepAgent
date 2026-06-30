from sleep_ai_scientist.common.config import config_path, load_config
from sleep_ai_scientist.grounding.data_profile import build_analysis_ready_profile, build_observed_profile
from sleep_ai_scientist.grounding.evidence_extractor import extract_evidence
from sleep_ai_scientist.grounding.evidence_grader import grade_evidence_records
from sleep_ai_scientist.grounding.literature_loader import load_literature
from sleep_ai_scientist.grounding.mechanism_graph import build_mechanism_graph
from sleep_ai_scientist.grounding.variable_mapper import map_variables


def test_mechanism_graph_contains_nodes_and_edges():
    config = load_config("configs/grounding_config.yaml")
    papers = load_literature("data/fixtures/toy_seed_papers.csv")
    evidence = grade_evidence_records(extract_evidence(papers))
    ready = build_analysis_ready_profile(config, build_observed_profile(config))
    mappings = map_variables(evidence, ready, config_path(config, "variable_mapping_rules"))
    nodes, edges = build_mechanism_graph(papers, evidence, mappings, config_path(config, "mechanism_templates"))
    assert nodes
    assert edges
    assert any(node.node_type.value == "Confound" for node in nodes)
