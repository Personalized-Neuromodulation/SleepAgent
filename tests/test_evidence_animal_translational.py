from sleep_ai_scientist.grounding.evidence_extractor import extract_evidence
from sleep_ai_scientist.grounding.evidence_grader import grade_evidence_records
from sleep_ai_scientist.schemas.literature import LiteratureRecord


def test_mouse_optogenetic_orexin_is_translational_not_direct_human():
    paper = LiteratureRecord(
        paper_id="mouse1",
        title="Orexin optogenetic study",
        abstract="Optogenetic stimulation of orexin neurons in mice increased wakefulness and altered NREM sleep transitions.",
    )
    evidence = grade_evidence_records(extract_evidence([paper]))
    orexin = next(item for item in evidence if item.mechanism == "orexin_hypocretin_arousal")
    assert orexin.species == "mouse"
    assert orexin.evidence_context == "animal_mechanistic"
    assert orexin.downstream_role != "direct_human_evidence"
    assert orexin.mechanistic_strength_score and orexin.mechanistic_strength_score > orexin.clinical_applicability_score


def test_animal_mechanisms_are_recognized():
    paper = LiteratureRecord(
        paper_id="animal2",
        title="Sleep mechanisms",
        abstract="GABAergic VLPO neurons promote sleep. Adenosine sleep pressure and glymphatic clearance were studied in rats.",
    )
    mechanisms = {item.mechanism for item in extract_evidence([paper])}
    assert "gabaergic_sleep_promotion" in mechanisms
    assert "adenosine_sleep_pressure" in mechanisms
    assert "glymphatic_clearance" in mechanisms
