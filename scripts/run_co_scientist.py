from __future__ import annotations

import argparse
import json

from sleep_ai_scientist.hypothesis.co_scientist_pipeline import run_co_scientist_pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/co_scientist_config.yaml")
    args = parser.parse_args()
    print(json.dumps(run_co_scientist_pipeline(args.config), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
