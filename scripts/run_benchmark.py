from __future__ import annotations

import argparse
import json

from sleep_ai_scientist.benchmark.benchmark_pipeline import run_benchmark_pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/benchmark_config.yaml")
    args = parser.parse_args()
    print(json.dumps(run_benchmark_pipeline(args.config), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
