from sleep_ai_scientist.foundation.qc_integrator import load_qc_records, normalize_qc_status, qc_counts
from sleep_ai_scientist.schemas.foundation import QCStatus
from tests.config_helpers import toy_foundation_config


def test_qc_status_normalization():
    config = toy_foundation_config()
    assert normalize_qc_status("PASS", config) == QCStatus.pass_
    assert normalize_qc_status("partial", config) == QCStatus.caution
    assert normalize_qc_status("FAIL", config) == QCStatus.fail
    assert normalize_qc_status("weird", config) == QCStatus.unknown


def test_qc_missing_file_does_not_crash(tmp_path):
    config = toy_foundation_config()
    config["inputs"]["qc_summary"] = str(tmp_path / "missing.csv")
    records = load_qc_records(config, ["S001"])
    assert records[0].qc_status == QCStatus.unknown


def test_qc_counts_by_modality():
    config = toy_foundation_config()
    counts = qc_counts(load_qc_records(config))
    assert counts["DTI"]["fail"] == 1
