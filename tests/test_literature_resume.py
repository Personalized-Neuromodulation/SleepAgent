from sleep_ai_scientist.literature.checkpoint import write_checkpoint
from sleep_ai_scientist.literature.long_run_supervisor import run_long_run


def test_long_run_resume_from_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("SLEEPAGENT_SQLITE_PATH", str(tmp_path / "resume.db"))
    checkpoint = write_checkpoint(tmp_path, {"run_id": "r1", "run_dir": str(tmp_path), "status": "ok"}, iteration=1)
    result = run_long_run("configs/literature_long_run_config.yaml", resume=checkpoint, dry_run=True, backend="sqlite")
    assert result["run_id"] == "r1"
    assert result["iterations_completed"] == 1

