from pathlib import Path

from sleep_ai_scientist.knowledge_sources.registry_builder import build_knowledge_sources, export_knowledge_sources


def test_knowledge_sources_exporters_write_files(monkeypatch, tmp_path):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "knowledge_export.db"))
    build_knowledge_sources("configs/knowledge_sources_config.yaml", backend="sqlite")
    result = export_knowledge_sources("configs/knowledge_sources_config.yaml", backend="sqlite")
    assert result["output_files"]["guidelines"]["count"] > 0
    assert Path("outputs/knowledge_sources/knowledge_sources_manifest.json").exists()
    assert Path("outputs/knowledge_sources/knowledge_sources_report.md").exists()

