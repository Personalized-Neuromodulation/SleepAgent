from sleep_ai_scientist.literature.checkpoint import get_latest_checkpoint, load_checkpoint, write_checkpoint


def test_literature_checkpoint_roundtrip(tmp_path):
    path = write_checkpoint(tmp_path, {"run_id": "r1", "status": "ok"}, iteration=1)
    assert path.exists()
    latest = get_latest_checkpoint(tmp_path)
    assert latest.exists()
    payload = load_checkpoint(latest)
    assert payload["run_id"] == "r1"

