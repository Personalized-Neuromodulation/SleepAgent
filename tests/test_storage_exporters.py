from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope
from sleep_ai_scientist.storage.exporters import export_literature_registry_csv_jsonl
from sleep_ai_scientist.storage.repositories import PaperRepository


def test_exporters_write_csv_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "export.db"))
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    with session_scope(engine) as session:
        PaperRepository().upsert_paper(session, LiteratureRecord(paper_id="p1", title="Sleep EEG", keywords=["EEG"]))
        result = export_literature_registry_csv_jsonl(session, tmp_path / "registry.csv", tmp_path / "registry.jsonl")
    assert result["paper_count"] == 1
    assert (tmp_path / "registry.csv").exists()
    assert (tmp_path / "registry.jsonl").read_text().count("\n") == 1
    engine.dispose()


def test_literature_registry_exporter_can_write_csv_only(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "export.db"))
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    with session_scope(engine) as session:
        PaperRepository().upsert_paper(session, LiteratureRecord(paper_id="p1", title="Sleep EEG", keywords=["EEG"]))
        result = export_literature_registry_csv_jsonl(session, tmp_path / "registry.csv")
    assert result == {"paper_count": 1, "csv": str(tmp_path / "registry.csv")}
    assert (tmp_path / "registry.csv").exists()
    assert not (tmp_path / "registry.jsonl").exists()
    engine.dispose()
