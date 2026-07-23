from sleep_ai_scientist.foundation.qc_integrator import load_qc_records
from sleep_ai_scientist.foundation.subject_index import build_subject_index
from sleep_ai_scientist.foundation.utils import normalize_subject_rows
from tests.config_helpers import toy_foundation_config


def test_subject_id_normalization_alias():
    config = toy_foundation_config()
    rows = normalize_subject_rows([{"sub_id": "S001", "group": "INS"}], config)
    assert rows[0]["subject_id"] == "S001"


def test_subject_index_modality_flags():
    config = toy_foundation_config()
    rows = build_subject_index(config, load_qc_records(config))
    first = rows[0]
    assert {"subject_id", "has_EEG", "has_fMRI", "available_modalities", "overall_qc_status"} <= set(first)
    assert first["has_EEG"] is True
    assert "EEG" in first["available_modalities"]
