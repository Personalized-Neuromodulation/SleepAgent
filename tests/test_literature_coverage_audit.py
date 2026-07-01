from sleep_ai_scientist.literature.coverage_audit import build_coverage_audit
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_coverage_audit_identifies_empty_groups():
    records = [LiteratureRecord(paper_id="p1", title="Human sleep EEG", abstract="human EEG sleep")]
    audit = build_coverage_audit(records, ["human_sleep_eeg_psg", "animal_causal_sleep"])
    assert "animal_causal_sleep" in audit["empty_query_groups"]
    assert audit["human_count"] == 1

