#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 Grounding API Build v1.")
    parser.add_argument("--grounding-config", default="configs/grounding_config.yaml")
    parser.add_argument("--query-config", default="configs/literature_queries.yaml")
    parser.add_argument("--corpus-version", default="sleepagent_grounding_corpus_v1")
    args = parser.parse_args()
    result = run_grounding_pipeline(
        args.grounding_config,
        query_config_path=args.query_config,
        corpus_version=args.corpus_version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
