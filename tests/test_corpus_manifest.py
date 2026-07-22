from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.grounding.corpus_manifest import build_corpus_manifest


def test_build_corpus_manifest_contains_version_and_paths():
    config = load_config("configs/grounding_config.yaml")
    config["query_set"] = {"version": "sleepagent_literature_queries_v1"}
    config["api"]["enabled"] = True

    manifest = build_corpus_manifest(config, "sleepagent_grounding_corpus_v1", {"query_results": []})

    assert manifest["corpus_version"] == "sleepagent_grounding_corpus_v1"
    assert manifest["query_set_version"] == "sleepagent_literature_queries_v1"
    assert manifest["final_literature_registry"].endswith("outputs/grounding/grounding_literature_registry.csv")
