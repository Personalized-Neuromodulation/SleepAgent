from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.literature.iterative_builder import run_iteration


def test_iterative_builder_dry_iteration(tmp_path):
    config = load_config("configs/literature_long_run_config.yaml")
    result = run_iteration(config, 1, tmp_path, dry_run=True, backend="sqlite")
    assert result["status"] == "planned"
    assert result["planned_max_queries"] > 0

