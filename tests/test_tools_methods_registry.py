from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.knowledge_sources.tools_methods import build_tool_method_records


def test_tools_methods_registry_contains_yasa_bids():
    records = build_tool_method_records(load_config("configs/knowledge_sources_config.yaml"))
    names = {record["name"] for record in records}
    assert {"YASA", "BIDS", "spindle_detection"} <= names

