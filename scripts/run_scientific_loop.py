from __future__ import annotations

import argparse
import json

from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hypothesis-config", default="configs/hypothesis_config.yaml")
    parser.add_argument("--experiment-config", default="configs/experiment_config.yaml")
    args = parser.parse_args()
    result = {
        "hypothesis": run_hypothesis_pipeline(args.hypothesis_config),
        "experiment": run_experiment_pipeline(args.experiment_config),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
