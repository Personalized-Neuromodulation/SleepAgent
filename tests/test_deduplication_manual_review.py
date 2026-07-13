from pathlib import Path

from sleep_ai_scientist.literature.identity_resolution import export_deduplication_artifacts, resolve_and_upsert
from sleep_ai_scientist.schemas.literature import LiteratureRecord
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope


def test_doi_conflict_similar_title_enters_manual_review(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "lit.db"))
    engine = create_engine_from_config("configs/database_config.yaml", backend="sqlite")
    init_database(engine)
    with session_scope(engine) as session:
        resolve_and_upsert(
            LiteratureRecord(paper_id="a", title="Sleep duration and cardiometabolic risk", doi="10.1/a", year=2024, journal="Sleep"),
            session,
            retrieval_channel="api_broad",
        )
        result = resolve_and_upsert(
            LiteratureRecord(paper_id="b", title="Sleep duration and cardiometabolic risks", doi="10.1/b", year=2024, journal="Sleep"),
            session,
            retrieval_channel="journal_targeted",
        )
        artifacts = export_deduplication_artifacts(
            session,
            tmp_path / "report.csv",
            tmp_path / "summary.json",
            tmp_path / "manual.csv",
        )

        assert result.action == "manual_review_needed"
        assert artifacts["summary"]["manual_review_count"] == 1
        assert Path(tmp_path / "manual.csv").read_text(encoding="utf-8").count("manual_review") >= 1
    engine.dispose()

