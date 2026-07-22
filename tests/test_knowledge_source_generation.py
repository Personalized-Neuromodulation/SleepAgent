from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path


def test_knowledge_sources_build_from_current_project(monkeypatch, tmp_path):
    from sleep_ai_scientist.knowledge_sources import registry_builder

    module_path = Path(inspect.getfile(registry_builder)).resolve()
    assert Path.cwd().resolve() in module_path.parents

    db_path = tmp_path / "knowledge_sources.db"
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(db_path))

    result = registry_builder.build_knowledge_sources("configs/knowledge_sources_config.yaml", backend="sqlite")

    assert db_path.exists()
    assert result["guidelines_count"] > 0
    assert result["standards_count"] > 0
    assert result["diagnostic_terms_count"] > 0
    assert result["datasets_count"] > 0
    assert result["instruments_count"] > 0
    assert result["tools_methods_count"] > 0

    with sqlite3.connect(db_path) as conn:
        counts = {
            table: conn.execute(f"select count(*) from {table}").fetchone()[0]
            for table in (
                "guidelines",
                "standards_rules",
                "diagnostic_terms",
                "datasets",
                "instruments",
                "tools_methods",
                "build_runs",
            )
        }

    assert all(count > 0 for count in counts.values())
    assert Path("outputs/knowledge_sources/knowledge_sources_manifest.json").exists()
    assert Path("outputs/knowledge_sources/knowledge_sources_report.md").exists()


def test_knowledge_source_build_entrypoints_are_wired():
    script = Path("scripts/run_foundation_grounding_online.sh").read_text(encoding="utf-8")

    assert "python -m sleep_ai_scientist.cli knowledge build" in script
    assert "configs/knowledge_sources_config.yaml" in script
    assert "select count(*) from guidelines" in script
    assert "select count(*) from diagnostic_terms" in script


def test_scripts_do_not_keep_redundant_python_build_wrappers():
    redundant_wrappers = {
        "build_knowledge_sources.py",
        "build_sleep_literature_library.py",
        "run_data_foundation.py",
    }
    script_names = {path.name for path in Path("scripts").glob("*.py")}
    assert script_names.isdisjoint(redundant_wrappers)
