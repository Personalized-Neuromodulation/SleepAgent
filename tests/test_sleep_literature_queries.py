from pathlib import Path

import pytest

from sleep_ai_scientist.literature.query_loader import load_query_set
from sleep_ai_scientist.common.io import read_yaml


def test_literature_queries_expose_single_broad_library_scope():
    raw_payload = read_yaml(Path("configs/literature_queries.yaml"))
    assert set(raw_payload["query_sets"]) == {"library"}

    payload, queries = load_query_set("configs/literature_queries.yaml", scope="library")
    groups = set(payload["queries"])
    assert "general_sleep_physiology" in groups
    assert "animal_causal_sleep" in groups
    assert "molecular_cellular_sleep" in groups
    assert "human_sleep_neuroimaging" in groups
    assert "insomnia_clinical_application" in groups
    assert len(queries) >= 100
    assert payload["scope"] == "library"


def test_grounding_query_scope_is_not_supported():
    with pytest.raises(KeyError):
        load_query_set("configs/literature_queries.yaml", scope="grounding")
