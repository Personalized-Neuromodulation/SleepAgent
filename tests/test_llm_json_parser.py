from sleep_ai_scientist.llm.json_parser import parse_json_object


def test_parse_json_object_from_fence():
    assert parse_json_object('```json\n{"verified_claims": []}\n```') == {"verified_claims": []}
