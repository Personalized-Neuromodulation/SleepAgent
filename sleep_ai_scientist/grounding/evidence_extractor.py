from __future__ import annotations

from pathlib import Path

from sleep_ai_scientist.common.io import write_csv, write_json
from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord, EvidenceType
from sleep_ai_scientist.schemas.literature import LiteratureRecord


# Phase 1 uses transparent keyword rules rather than an LLM extractor. Each
# tuple maps a literature term to modality, measurable variable, and mechanism.
RULES = [
    ("slow wave", "EEG", "slow_wave_density", "slow-wave generation"),
    ("delta", "EEG", "delta_power", "slow-wave generation"),
    ("spindle", "EEG", "spindle_density", "spindle generation"),
    ("thalamocortical", "EEG-fMRI", "thalamus_DMN_FC", "thalamocortical coupling"),
    ("default mode network", "fMRI", "thalamus_DMN_FC", "thalamocortical coupling"),
    ("dmn", "fMRI", "thalamus_DMN_FC", "thalamocortical coupling"),
    ("dti", "DTI", "FA", "white matter integrity"),
    (" fa", "DTI", "FA", "white matter integrity"),
    ("mri", "MRI", "MRI", "structural morphology"),
    ("hippocampus", "MRI", "hippocampus_volume", "hippocampal morphology"),
    ("thalamus", "MRI", "thalamus_volume", "thalamic morphology"),
    ("isi", "Scale", "ISI", "insomnia severity"),
    ("psqi", "Scale", "PSQI", "insomnia severity"),
    ("hyperarousal", "EEG", "beta_power", "hyperarousal"),
    ("beta", "EEG", "beta_power", "hyperarousal"),
    ("salience", "fMRI", "salience_network_FC", "salience network regulation"),
]


def infer_evidence_type(text: str) -> EvidenceType:
    """Infer coarse study type from text cues."""
    lowered = text.lower()
    if "meta-analysis" in lowered or "meta analysis" in lowered:
        return EvidenceType.meta_analysis
    if "review" in lowered:
        return EvidenceType.review
    if "case" in lowered:
        return EvidenceType.case
    if "method" in lowered:
        return EvidenceType.method
    if "empirical" in lowered or "study" in lowered or "findings" in lowered:
        return EvidenceType.empirical
    return EvidenceType.unknown


def infer_direction(text: str) -> EvidenceDirection:
    """Classify whether a claim supports, refutes, or fails to support a mechanism."""
    lowered = text.lower()
    if any(term in lowered for term in ["no association", "not associated", "null finding"]):
        return EvidenceDirection.null
    if any(term in lowered for term in ["refute", "opposite", "lower than expected"]):
        return EvidenceDirection.refute
    if any(term in lowered for term in ["associated", "support", "suggest", "show", "reports", "reduced", "increased", "altered", "disrupted"]):
        return EvidenceDirection.support
    return EvidenceDirection.unclear


def extract_population(text: str, default: str = "") -> str:
    """Extract a minimal population label; config supplies the fallback."""
    lowered = text.lower()
    if "insomnia" in lowered:
        return "insomnia"
    if "sleep disorder" in lowered:
        return "sleep disorder"
    if "adults" in lowered:
        return "adults"
    return default


def extract_limitation(text: str) -> str:
    """Capture simple limitation phrases for evidence quality grading."""
    lowered = text.lower()
    marker = "limitation:"
    if marker in lowered:
        idx = lowered.index(marker) + len(marker)
        return text[idx:].strip()
    for phrase in ["small sample", "cross-sectional"]:
        if phrase in lowered:
            return phrase
    return ""


def extract_evidence(records: list[LiteratureRecord], default_population: str = "") -> list[EvidenceRecord]:
    """Extract one evidence row per matched keyword/mechanism rule."""
    evidence: list[EvidenceRecord] = []
    for record in records:
        text = " ".join([record.title, record.abstract, " ".join(record.keywords), record.notes])
        lowered = f" {text.lower()} "
        for keyword, modality, variable, mechanism in RULES:
            if keyword in lowered:
                claim = f"{record.title}: {mechanism} related to {variable}"
                evidence.append(
                    EvidenceRecord(
                        evidence_id=stable_id("evidence", record.paper_id, mechanism, variable),
                        paper_id=record.paper_id,
                        claim=claim,
                        population=extract_population(text, default_population),
                        modality=modality,
                        variable_or_feature=variable,
                        mechanism=mechanism,
                        direction=infer_direction(text),
                        evidence_type=infer_evidence_type(text),
                        limitation=extract_limitation(text),
                        confidence_score=0.7,
                    )
                )
    return evidence


def write_evidence_outputs(evidence: list[EvidenceRecord], out_dir: Path) -> None:
    """Write the Phase 1 evidence table in both tabular and JSON formats."""
    rows = [item.model_dump(mode="json") for item in evidence]
    write_csv(out_dir / "evidence_table.csv", rows)
    write_json(out_dir / "evidence_table.json", rows)
