from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.foundation.master_table import build_multimodal_master_table
from sleep_ai_scientist.foundation.qc_integrator import load_qc_records
from sleep_ai_scientist.foundation.subject_index import build_subject_index


def test_master_table_merges_on_subject_id():
    config = load_config("configs/foundation_config.yaml")
    subject_rows = build_subject_index(config, load_qc_records(config))
    rows, log = build_multimodal_master_table(config, subject_rows)
    assert len(rows) == 5
    assert "subject_id" in rows[0]
    assert "slow_wave_density" in rows[0]
    assert "thalamus_DMN_FC" in rows[0]
    assert log["input_file_count"] == 5
