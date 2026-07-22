from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.config import project_root
from sleep_ai_scientist.common.io import read_yaml, write_csv, write_json
from sleep_ai_scientist.common.utils import stable_id
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord, EvidenceType
from sleep_ai_scientist.schemas.literature import LiteratureRecord


DEFAULT_RULES_PATH = project_root() / "configs/evidence_extraction_rules.yaml"
SPECULATIVE_TERMS = {"may", "might", "could", "hypothesized", "proposed"}
MECHANISMS_IN_SCOPE = {
    "slow-wave generation",
    "spindle generation",
    "hyperarousal",
    "thalamocortical coupling",
    "default mode network dysregulation",
    "salience network dysregulation",
    "white matter integrity",
    "limbic structural vulnerability",
    "insomnia severity",
    "sleep quality",
}


def load_evidence_rules(path: str | Path | None = None) -> dict[str, Any]:
    """Load deterministic evidence extraction rules."""
    rule_path = Path(path) if path else DEFAULT_RULES_PATH
    return read_yaml(rule_path)


def split_sentences(text: str) -> list[str]:
    """Split lightweight abstract text into candidate evidence sentences."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]


def _contains(text: str, term: str) -> bool:
    return term.lower() in text.lower()


def _matched(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if _contains(text, str(term))]


def infer_evidence_type(text: str) -> EvidenceType:
    lowered = text.lower()
    if "meta-analysis" in lowered or "meta analysis" in lowered:
        return EvidenceType.meta_analysis
    if "systematic review" in lowered:
        return EvidenceType.systematic_review
    if "review" in lowered:
        return EvidenceType.review
    if "case" in lowered:
        return EvidenceType.case
    if "method" in lowered or "protocol" in lowered:
        return EvidenceType.method
    if any(term in lowered for term in ["study", "trial", "cohort", "participants", "patients", "mice", "rats"]):
        return EvidenceType.empirical
    return EvidenceType.unknown


def infer_direction(text: str, rules: dict[str, Any] | None = None) -> EvidenceDirection:
    lowered = text.lower()
    terms = (rules or {}).get("direction_terms", {})
    if any(term in lowered for term in terms.get("refute", [])):
        return EvidenceDirection.refute
    if any(term in lowered for term in terms.get("null", [])):
        return EvidenceDirection.null
    if any(term in lowered for term in terms.get("support", [])):
        return EvidenceDirection.support
    return EvidenceDirection.unclear


def infer_effect_direction(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ["no significant", "no difference", "no association", "not associated"]):
        return "no_difference"
    if any(term in lowered for term in ["increased", "higher", "elevated"]):
        return "increased"
    if any(term in lowered for term in ["reduced", "decreased", "lower"]):
        return "decreased"
    if "associated" in lowered or "association" in lowered:
        return "associated"
    if "altered" in lowered or "disrupted" in lowered:
        return "altered"
    return "unknown"


def extract_population(text: str, default: str = "") -> str:
    lowered = text.lower()
    if "insomnia" in lowered:
        return "insomnia"
    if "poor sleeper" in lowered or "sleep complaint" in lowered:
        return "poor sleepers"
    if "healthy" in lowered and "human" in lowered:
        return "healthy human"
    if any(term in lowered for term in ["participants", "patients", "adults"]):
        return "human"
    return default


def infer_species(text: str, rules: dict[str, Any]) -> tuple[str, list[str]]:
    animal_terms = rules.get("animal_terms", {}).get("species", {})
    hits: list[tuple[str, str]] = []
    for species, terms in animal_terms.items():
        for term in terms:
            if _contains(text, term):
                hits.append((species, term))
    if len({species for species, _ in hits}) > 1:
        return "mixed", [term for _, term in hits]
    if hits:
        return hits[0][0], [term for _, term in hits]
    if any(term in text.lower() for term in ["human", "patient", "participant", "adult", "insomnia"]):
        return "human", ["human"]
    return "unknown", []


def infer_model_system(text: str, rules: dict[str, Any], species: str) -> tuple[str, str, list[str]]:
    lowered = text.lower()
    model_hits: list[str] = []
    for model, terms in rules.get("animal_terms", {}).get("models", {}).items():
        if any(term.lower() in lowered for term in terms):
            model_hits.append(model)
    if "optogenetic" in model_hits:
        model = "optogenetic_model"
    elif "pharmacological" in model_hits:
        model = "pharmacological_model"
    elif "sleep_deprivation" in model_hits:
        model = "sleep_deprivation_model"
    elif "lesion" in model_hits:
        model = "lesion_model"
    elif "electrophysiology" in model_hits:
        model = "electrophysiology"
    elif "calcium_imaging" in model_hits:
        model = "calcium_imaging"
    elif species in {"mouse", "rat", "cat", "nonhuman_primate", "animal", "mixed"}:
        model = "rodent_sleep" if species in {"mouse", "rat"} else "unknown"
    elif species == "human" and "insomnia" in lowered:
        model = "human_patient"
    elif species == "human":
        model = "healthy_human"
    else:
        model = "unknown"
    if model in {"optogenetic_model", "pharmacological_model", "sleep_deprivation_model", "lesion_model", "rodent_sleep", "electrophysiology", "calcium_imaging"}:
        context = "animal_mechanistic"
    elif species == "human" and any(term in lowered for term in ["fmri", "mri", "dti", "neuroimaging"]):
        context = "human_neuroimaging"
    elif species == "human" and "insomnia" in lowered:
        context = "human_clinical"
    elif species == "human":
        context = "human_general_sleep"
    else:
        context = "unknown"
    return model, context, model_hits


def infer_study_design(text: str) -> tuple[str, str]:
    lowered = text.lower()
    if "randomized" in lowered:
        return "randomized", "unknown"
    if "longitudinal" in lowered:
        return "longitudinal", "unknown"
    if "case-control" in lowered or "case control" in lowered:
        return "case_control", "unknown"
    if "cohort" in lowered:
        return "cohort", "unknown"
    if "cross-sectional" in lowered:
        return "cross_sectional", "unknown"
    if "optogenetic" in lowered:
        return "observational", "optogenetic_causal_manipulation"
    if "chemogenetic" in lowered or "dreadd" in lowered:
        return "observational", "chemogenetic_causal_manipulation"
    if "sleep deprivation" in lowered:
        return "observational", "sleep_deprivation_model"
    if any(term in lowered for term in ["fmri", "mri", "dti"]):
        return "observational", "human_neuroimaging"
    if "psg" in lowered or "eeg" in lowered:
        return "observational", "human_psg"
    return "unknown", "unknown"


def infer_limitations(text: str, rules: dict[str, Any]) -> tuple[list[str], list[str]]:
    lowered = text.lower()
    limitations = [term for term in rules.get("limitation_terms", []) if term in lowered]
    confounds = [term for term in rules.get("confound_terms", []) if term in lowered]
    return limitations, confounds


def extract_sample_size(text: str) -> tuple[int | None, str | None]:
    match = re.search(r"\b[nN]\s*=\s*(\d+)\b", text)
    if not match:
        match = re.search(r"\b(\d+)\s+(participants|patients|mice|rats|subjects)\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1)), match.group(0)
    return None, None


def _publication_metadata(record: LiteratureRecord) -> dict[str, Any]:
    return {
        "query_source": record.source,
        "provider": record.provider,
        "doi": record.doi or None,
        "pmid": record.pmid or None,
        "journal": record.journal,
        "publication_year": record.publication_year or record.year,
        "publication_type": record.publication_type,
        "citation_count": record.citation_count,
        "citation_source": record.citation_source,
        "citation_count_age_normalized": record.citation_count_age_normalized,
        "journal_impact_factor": record.journal_impact_factor,
        "journal_impact_factor_year": record.journal_impact_factor_year,
        "journal_quartile": record.journal_quartile,
        "journal_metric_source": record.journal_metric_source,
        "is_open_access": record.is_open_access,
    }


def _data_hint(mechanism: str, variable: str, context: str) -> str:
    if mechanism not in MECHANISMS_IN_SCOPE:
        return "theory_only"
    if variable:
        return "mapped_candidate"
    if context.startswith("animal") or context == "cellular_molecular":
        return "theory_only"
    return "unclear"


def _downstream_role(text: str, default: str, species: str, context: str, direction: EvidenceDirection) -> str:
    lowered = text.lower()
    if direction == EvidenceDirection.unclear and any(term in lowered for term in SPECULATIVE_TERMS):
        return "not_for_hypothesis_generation"
    if "confound" in lowered or "head motion" in lowered or "method" in lowered:
        return "critique_only"
    if species in {"mouse", "rat", "cat", "nonhuman_primate", "animal", "mixed"}:
        return "translational_mechanistic_support" if context == "animal_mechanistic" else "background_mechanism"
    if context == "cellular_molecular":
        return "background_mechanism"
    return default or "direct_human_evidence"


def _translational_fields(species: str, model_system: str, context: str) -> tuple[str, list[str]]:
    if species == "human":
        return "direct", []
    risks = []
    if species in {"mouse", "rat", "cat", "nonhuman_primate", "animal", "mixed"}:
        risks.extend(["species_difference", "small_animal_model" if species in {"mouse", "rat"} else "non_clinical_model"])
    if model_system == "sleep_deprivation_model":
        risks.append("artificial_sleep_deprivation")
    if context != "human_clinical":
        risks.append("no_direct_human_measure")
    relevance = "moderate" if context == "animal_mechanistic" else "indirect" if context == "cellular_molecular" else "unknown"
    return relevance, sorted(set(risks))


def _confidence(text: str, matched_terms: list[str], direction: EvidenceDirection, variable: str, method: str) -> tuple[float, str]:
    score = 0.25 if method == "fallback_title" else 0.55
    score += min(0.2, len(matched_terms) * 0.03)
    score += 0.1 if direction != EvidenceDirection.unclear else -0.08
    score += 0.08 if variable else -0.05
    if any(term in text.lower() for term in SPECULATIVE_TERMS):
        score -= 0.15
    if method == "fallback_title":
        score = min(score, 0.35)
    score = round(max(0.05, min(1.0, score)), 3)
    return score, f"{method}; matched_terms={len(matched_terms)}; direction={direction.value}"


def _sections(record: LiteratureRecord) -> list[tuple[str, list[str]]]:
    return [
        ("title", [record.title] if record.title else []),
        ("abstract", split_sentences(record.abstract)),
        ("notes", split_sentences(record.notes)),
    ]


def extract_evidence(
    records: list[LiteratureRecord],
    default_population: str = "",
    rules_path: str | Path | None = None,
    llm_verifier: Any | None = None,
    llm_config: dict[str, Any] | None = None,
) -> list[EvidenceRecord]:
    """Extract sentence-level evidence using deterministic rules plus optional verifier."""
    rules = load_evidence_rules(rules_path)
    evidence: list[EvidenceRecord] = []
    seen_ids: set[str] = set()
    for record in records:
        paper_evidence = 0
        for section, sentences in _sections(record):
            if section == "title" and (record.abstract or record.notes):
                continue
            for sentence_index, sentence in enumerate(sentences):
                for mechanism, rule in rules.get("mechanisms", {}).items():
                    mechanism_hits = _matched(sentence, rule.get("mechanism_keywords", []))
                    variable_hits = _matched(sentence, rule.get("variable_keywords", []))
                    if not mechanism_hits and not variable_hits:
                        continue
                    method = "fallback_title" if section == "title" and not record.abstract else "rule"
                    direction = EvidenceDirection.unclear if method == "fallback_title" else infer_direction(sentence, rules)
                    species, species_terms = infer_species(sentence, rules)
                    model_system, context, model_terms = infer_model_system(sentence, rules, species)
                    if context == "unknown":
                        context = rule.get("evidence_context_default", "unknown")
                    study_design, study_design_detail = infer_study_design(sentence)
                    limitations, confounds = infer_limitations(sentence, rules)
                    sample_size, sample_note = extract_sample_size(sentence)
                    matched_terms = sorted(set(mechanism_hits + variable_hits + species_terms + model_terms))
                    modality = (rule.get("modalities") or [""])[0]
                    variable = variable_hits[0] if variable_hits else (rule.get("variable_keywords") or [""])[0]
                    population = extract_population(sentence, default_population)
                    downstream_role = _downstream_role(sentence, rule.get("downstream_role_default", ""), species, context, direction)
                    translational_relevance, translational_risk = _translational_fields(species, model_system, context)
                    extraction_confidence, confidence_reason = _confidence(sentence, matched_terms, direction, variable, method)
                    evidence_id = stable_id("E", record.paper_id, section, sentence_index, mechanism)
                    if evidence_id in seen_ids:
                        continue
                    seen_ids.add(evidence_id)
                    record_payload = EvidenceRecord(
                        evidence_id=evidence_id,
                        paper_id=record.paper_id,
                        claim=f"{sentence} [{mechanism}]",
                        population=population,
                        modality=modality,
                        variable_or_feature=variable,
                        mechanism=mechanism,
                        direction=direction,
                        evidence_type=infer_evidence_type(" ".join([record.title, sentence, record.notes])),
                        limitation="; ".join(limitations),
                        confidence_score=extraction_confidence,
                        source_text=sentence,
                        section=section,
                        sentence_index=sentence_index,
                        matched_terms=matched_terms,
                        extraction_method=method,
                        condition="insomnia" if "insomnia" in sentence.lower() else None,
                        comparison_group="control" if "control" in sentence.lower() else None,
                        effect_direction=infer_effect_direction(sentence),
                        study_design=study_design,
                        study_design_detail=study_design_detail,
                        sample_size_total=sample_size,
                        sample_size_note=sample_note,
                        species=species,
                        limitations=limitations,
                        confounds=confounds,
                        causal_inference_limit=study_design_detail not in {"optogenetic_causal_manipulation", "chemogenetic_causal_manipulation"},
                        overclaim_risk=0.7 if downstream_role == "not_for_hypothesis_generation" else 0.3 if limitations or confounds else 0.1,
                        model_system=model_system,
                        evidence_context=context,
                        translational_relevance=translational_relevance,
                        translational_risk=translational_risk,
                        downstream_role=downstream_role,
                        data_mappability_hint=_data_hint(mechanism, variable, context),
                        mechanism_in_scope=mechanism in MECHANISMS_IN_SCOPE,
                        extraction_confidence_score=extraction_confidence,
                        confidence_reason=confidence_reason,
                        **_publication_metadata(record),
                    )
                    evidence.append(record_payload)
                    paper_evidence += 1
        # Low-confidence title fallback when a title has a mechanism but no abstract/notes evidence.
        if paper_evidence == 0 and record.title:
            title_lower = record.title.lower()
            for mechanism, rule in rules.get("mechanisms", {}).items():
                mechanism_hits = _matched(record.title, rule.get("mechanism_keywords", []))
                if mechanism_hits:
                    matched_terms = sorted(set(mechanism_hits))
                    extraction_confidence, confidence_reason = _confidence(record.title, matched_terms, EvidenceDirection.unclear, "", "fallback_title")
                    evidence.append(
                        EvidenceRecord(
                            evidence_id=stable_id("E", record.paper_id, "title", 0, mechanism),
                            paper_id=record.paper_id,
                            claim=f"{record.title} [{mechanism}]",
                            population=extract_population(record.title, default_population),
                            modality=(rule.get("modalities") or [""])[0],
                            variable_or_feature=(rule.get("variable_keywords") or [""])[0],
                            mechanism=mechanism,
                            direction=EvidenceDirection.unclear,
                            evidence_type=infer_evidence_type(record.title),
                            confidence_score=extraction_confidence,
                            source_text=record.title,
                            section="title",
                            sentence_index=0,
                            matched_terms=matched_terms,
                            extraction_method="fallback_title",
                            extraction_confidence_score=extraction_confidence,
                            confidence_reason=confidence_reason,
                            species="human" if "insomnia" in title_lower else "unknown",
                            evidence_context=rule.get("evidence_context_default", "unknown"),
                            downstream_role="not_for_hypothesis_generation",
                            data_mappability_hint="unclear",
                            **_publication_metadata(record),
                        )
                    )
                    break
    if llm_config and llm_config.get("evidence_extraction", {}).get("llm_assist_enabled", False) and llm_verifier:
        evidence = llm_verifier.verify(evidence, rules)
    return [item for item in evidence if item.source_text]


def _csv_safe(row: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in row.items():
        if isinstance(value, (list, dict)):
            safe[key] = json.dumps(value, ensure_ascii=False)
        else:
            safe[key] = value
    return safe


def write_evidence_outputs(evidence: list[EvidenceRecord], out_dir: Path) -> None:
    rows = [item.model_dump(mode="json") for item in evidence]
    write_csv(out_dir / "evidence_table.csv", [_csv_safe(row) for row in rows])
    write_json(out_dir / "evidence_table.json", rows)
