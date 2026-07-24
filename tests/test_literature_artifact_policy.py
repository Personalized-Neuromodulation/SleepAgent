from __future__ import annotations

from pathlib import Path

from sleep_ai_scientist.common.io import read_yaml


def _is_under_data_literature(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and path.parts[:2] == ("data", "literature")


def test_default_configs_keep_data_literature_canonical_only():
    allowed_data_literature_paths = {
        "data/literature/sleep_literature.db",
        "data/literature",
        "data/literature/sleep_literature_registry.csv",
    }
    configs = [
        read_yaml(Path("configs/grounding_config.yaml")),
        read_yaml(Path("configs/literature_library_config.yaml")),
        read_yaml(Path("configs/database_config.yaml")),
    ]

    offenders: list[str] = []
    for config in configs:
        for section in ("paths", "output"):
            for key, value in config.get(section, {}).items():
                if isinstance(value, str) and _is_under_data_literature(value) and value not in allowed_data_literature_paths:
                    offenders.append(f"{section}.{key}={value}")
        api_output = config.get("api", {}).get("output", {})
        for key, value in api_output.items():
            if isinstance(value, str) and _is_under_data_literature(value) and value not in allowed_data_literature_paths:
                offenders.append(f"api.output.{key}={value}")
        database = config.get("database", {})
        sqlite_path = database.get("default_sqlite_path")
        if isinstance(sqlite_path, str) and _is_under_data_literature(sqlite_path) and sqlite_path not in allowed_data_literature_paths:
            offenders.append(f"database.default_sqlite_path={sqlite_path}")

    assert offenders == []


def test_default_literature_configs_do_not_use_seed_inputs():
    configs = [
        read_yaml(Path("configs/grounding_config.yaml")),
        read_yaml(Path("configs/literature_library_config.yaml")),
    ]

    offenders: list[str] = []
    for config in configs:
        paths = config.get("paths", {})
        for key in ("seed_papers", "fixture_seed_papers"):
            if key in paths:
                offenders.append(f"paths.{key}={paths[key]}")
        deduplication = config.get("deduplication", {})
        if "seed_papers_priority" in deduplication:
            offenders.append(f"deduplication.seed_papers_priority={deduplication['seed_papers_priority']}")

    assert offenders == []


def test_default_config_ownership_for_db_first_rag():
    grounding = read_yaml(Path("configs/grounding_config.yaml"))
    literature = read_yaml(Path("configs/literature_library_config.yaml"))
    hypothesis = read_yaml(Path("configs/hypothesis_config.yaml"))
    experiment = read_yaml(Path("configs/experiment_config.yaml"))
    llm = read_yaml(Path("configs/llm_config.yaml"))

    assert "embedding" in literature
    assert "embedding" not in grounding
    assert "embedding" not in hypothesis
    assert grounding.get("api", {}) in ({}, {"enabled": False})
    assert "llm_context" not in grounding
    assert "llm_context_compression" in grounding
    assert "llm_provider" in llm
    assert "online_llm" in llm
    assert "ollama" in llm
    for module_config in (hypothesis, experiment):
        assert module_config.get("paths", {}).get("llm_config") == "configs/llm_config.yaml"
        assert "llm_provider" not in module_config
        assert "online_llm" not in module_config
        assert "ollama" not in module_config

    grounding_paths = grounding.get("paths", {})
    for key in grounding_paths:
        assert not key.startswith("fixture_")
        assert not key.startswith("api_")
    assert "fixtures_dir" not in grounding_paths
    assert "database_config" in grounding_paths
    assert "literature_library_config" in grounding_paths
