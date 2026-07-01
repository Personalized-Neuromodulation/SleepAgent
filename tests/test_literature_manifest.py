from sleep_ai_scientist.literature.manifest import build_library_manifest


def test_literature_manifest_contains_version_and_counts():
    manifest = build_library_manifest("lib_v1", "query_v1", {"registry_csv": "x.csv"}, {"paper_count": 1})
    assert manifest["library_version"] == "lib_v1"
    assert manifest["query_set_version"] == "query_v1"
    assert manifest["counts"]["paper_count"] == 1

