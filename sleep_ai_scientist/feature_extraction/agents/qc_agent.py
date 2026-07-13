from __future__ import annotations

from sleep_ai_scientist.feature_extraction.schemas import FeatureTable


class QCFeatureAgent:
    """Adds table-level QC metadata used by profile construction."""

    def run(self, tables: list[FeatureTable]) -> list[FeatureTable]:
        for table in tables:
            table.metadata["qc_status"] = table.metadata.get("qc_status", "pass")
        return tables
