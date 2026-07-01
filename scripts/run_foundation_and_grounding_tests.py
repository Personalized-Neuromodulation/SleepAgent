from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sleep_ai_scientist.foundation.foundation_pipeline import run_foundation_pipeline
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline


def main() -> int:
    foundation = run_foundation_pipeline("configs/foundation_config.yaml")
    grounding = run_grounding_pipeline("configs/grounding_config.yaml")
    print(
        json.dumps(
            {
                "foundation": {
                    "subject_count": foundation.get("subject_count"),
                    "feature_count": foundation.get("feature_count"),
                    "report": foundation.get("outputs", {}).get("report"),
                },
                "grounding": {
                    "papers": grounding.get("papers"),
                    "evidence": grounding.get("evidence"),
                    "api_enabled": grounding.get("api_summary", {}).get("enabled"),
                    "report_path": grounding.get("report_path"),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
