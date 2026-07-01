from pathlib import Path

from sleep_ai_scientist.grounding.evidence_benchmark import run_evidence_benchmark
from sleep_ai_scientist.schemas.evidence import EvidenceDirection, EvidenceRecord


def test_evidence_benchmark_outputs_species_and_downstream_metrics(tmp_path: Path):
    gold = tmp_path / "gold.csv"
    gold.write_text("paper_id,expected_mechanism,expected_direction,expected_modality,expected_variable_or_feature,expected_population,expected_species,expected_evidence_context,expected_downstream_role\np1,slow-wave generation,support,EEG,delta_power,insomnia,human,human_clinical,direct_human_evidence\n", encoding="utf-8")
    evidence = [EvidenceRecord(evidence_id="e1", paper_id="p1", claim="c", source_text="s", mechanism="slow-wave generation", direction=EvidenceDirection.support, modality="EEG", variable_or_feature="delta_power", species="human", evidence_context="human_clinical", downstream_role="direct_human_evidence")]
    result = run_evidence_benchmark(evidence, gold, tmp_path / "bench.json")
    assert result["species_accuracy"] == 1
    assert result["downstream_role_accuracy"] == 1
