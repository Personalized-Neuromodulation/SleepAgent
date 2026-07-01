from sleep_ai_scientist.common.config import load_config, resolve_path
from sleep_ai_scientist.common.io import read_csv
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline
from sleep_ai_scientist.hypothesis.registry import update_registry_status


def test_hypothesis_registry_status_update():
    result = run_hypothesis_pipeline("configs/hypothesis_config.yaml")
    registry = result["hypothesis_registry"]
    update_registry_status(registry, "H002", "tested")
    rows = read_csv(resolve_path(registry))
    assert any(row["hypothesis_id"] == "H002" and row["status"] == "tested" for row in rows)
    config = load_config("configs/hypothesis_config.yaml")
    assert resolve_path(config["outputs"]["hypothesis_lineage"]).exists()
