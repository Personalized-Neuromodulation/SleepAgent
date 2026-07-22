from sleep_ai_scientist.common.config import load_config


def test_knowledge_sources_config_has_all_paths():
    config = load_config("configs/knowledge_sources_config.yaml")
    paths = config["paths"]
    assert paths["clinical_trials_csv"].endswith(".csv")
    assert paths["diagnostic_taxonomy_yaml"].endswith(".yaml")
    assert config["standards"]["download_restricted_content"] is False

