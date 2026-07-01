from sleep_ai_scientist.literature.status_report import write_status_report


def test_status_report_written(tmp_path):
    path = write_status_report(tmp_path, 1, {"run_id": "r1", "total_records": 10})
    assert path.exists()
    assert "total records" in path.read_text()

