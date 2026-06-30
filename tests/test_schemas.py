from sleep_ai_scientist.schemas import EvidenceDirection, EvidenceRecord, LiteratureRecord, MappingStatus, VariableMappingRecord


def test_core_schemas_validate():
    paper = LiteratureRecord(paper_id="p1", title="Sleep paper")
    evidence = EvidenceRecord(evidence_id="e1", paper_id=paper.paper_id, claim="claim", direction=EvidenceDirection.support)
    mapping = VariableMappingRecord(concept="insomnia severity", approved_data_features=["ISI"], mapping_status=MappingStatus.mapped)
    assert paper.paper_id == "p1"
    assert evidence.direction == EvidenceDirection.support
    assert mapping.mapping_status == MappingStatus.mapped
