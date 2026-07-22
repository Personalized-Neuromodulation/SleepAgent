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
        "data/literature/sleep_literature_registry.jsonl",
    }
    configs = [
        read_yaml(Path("configs/grounding_config.yaml")),
        read_yaml(Path("configs/grounding_online_no_fixtures.yaml")),
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
        read_yaml(Path("configs/grounding_online_no_fixtures.yaml")),
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
