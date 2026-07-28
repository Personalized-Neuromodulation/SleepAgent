from sleep_ai_scientist.literature.long_run_supervisor import run_long_run


def test_literature_long_run_dry_generates_checkpoint(tmp_path):
    result = run_long_run("configs/literature_long_run_config.yaml", max_runtime_hours=0.25, dry_run=True, backend="postgresql")
    assert result["dry_run"] is True
    assert result["latest_checkpoint"]
