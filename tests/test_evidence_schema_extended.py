from sleep_ai_scientist.schemas.evidence import EvidenceRecord


def test_evidence_schema_extended_fields():
    record = EvidenceRecord(evidence_id="e1", paper_id="p1", claim="claim", source_text="source", matched_terms=["slow wave"])
    assert record.source_text == "source"
    assert record.matched_terms == ["slow wave"]
    assert record.extraction_method == "rule"
    assert record.llm_verified is False
    assert record.limitations == []
