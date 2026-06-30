#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SleepAgent Phase 1 grounding pipeline.")
    parser.add_argument("--config", default="configs/grounding_config.yaml")
    args = parser.parse_args()
    result = run_grounding_pipeline(args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
