from __future__ import annotations

from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import read_json
from sleep_ai_scientist.hypothesis.agents.supervisor_agent import HypothesisSupervisor
from sleep_ai_scientist.schemas.evidence import EvidenceRecord


def load_evidence_records(path: Path) -> list[EvidenceRecord]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return [EvidenceRecord(**row) for row in read_json(path)]


def run_hypothesis_pipeline(config_path_value: str | Path = "configs/hypothesis_config.yaml") -> dict[str, Any]:
    return HypothesisSupervisor().run(config_path_value)


def generate_hypothesis_report(config_path_value: str | Path = "configs/hypothesis_config.yaml") -> dict[str, Any]:
    return run_hypothesis_pipeline(config_path_value)
