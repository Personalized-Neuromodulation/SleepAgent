from sleep_ai_scientist.common.config import config_path, load_config
from sleep_ai_scientist.grounding.data_profile import build_analysis_ready_profile, build_observed_profile
from sleep_ai_scientist.grounding.evidence_extractor import extract_evidence
from sleep_ai_scientist.grounding.literature_loader import load_literature
from sleep_ai_scientist.grounding.variable_mapper import map_variables


def test_variable_mapping_marks_unavailable_without_real_column():
    config = load_config("configs/grounding_config.yaml")
    papers = load_literature("data/fixtures/toy_seed_papers.csv")
    evidence = extract_evidence(papers)
    ready = build_analysis_ready_profile(config, build_observed_profile(config))
    mappings = map_variables(evidence, ready, config_path(config, "variable_mapping_rules"))
    by_concept = {item.concept: item for item in mappings}
    assert by_concept["insomnia severity"].mapping_status.value in {"mapped", "ambiguous"}
    assert by_concept["structural morphology"].mapping_status.value == "unavailable"
