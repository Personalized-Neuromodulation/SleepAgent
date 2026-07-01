from sleep_ai_scientist.grounding.evidence_audit import build_evidence_audit
from sleep_ai_scientist.schemas.evidence import EvidenceRecord
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_evidence_audit_contains_species_and_context_counts():
    evidence = [EvidenceRecord(evidence_id="e1", paper_id="p1", claim="c", source_text="s", species="mouse", evidence_context="animal_mechanistic")]
    audit = build_evidence_audit([LiteratureRecord(paper_id="p1", title="t")], evidence, [])
    assert audit["species_counts"]["mouse"] == 1
    assert audit["evidence_context_counts"]["animal_mechanistic"] == 1
