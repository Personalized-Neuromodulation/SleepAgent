from sleep_ai_scientist.literature.error_recovery import is_recoverable_error, write_error_bundle


def test_error_bundle_can_be_written(tmp_path):
    assert is_recoverable_error("provider timeout")
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        bundle = write_error_bundle(tmp_path, exc, "stage1")
    assert (bundle / "error_summary.json").exists()
    assert (bundle / "traceback.txt").exists()

