from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.knowledge_sources.datasets import build_dataset_records


def test_datasets_registry_curated():
    records = build_dataset_records(load_config("configs/knowledge_sources_config.yaml"))
    names = {record["name"] for record in records}
    assert "Sleep-EDF" in names
    assert any(record["eeg_available"] for record in records)

