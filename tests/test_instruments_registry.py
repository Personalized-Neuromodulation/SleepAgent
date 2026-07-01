from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.knowledge_sources.instruments import build_instrument_records


def test_instruments_registry_contains_isi_psqi():
    records = build_instrument_records(load_config("configs/knowledge_sources_config.yaml"))
    ids = {record["abbreviation"] for record in records}
    assert {"ISI", "PSQI"} <= ids
    assert all(record["notes"] for record in records)

