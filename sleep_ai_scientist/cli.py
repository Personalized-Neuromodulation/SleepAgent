from __future__ import annotations

import argparse
import json

from sleep_ai_scientist.foundation.foundation_pipeline import generate_foundation_report, run_foundation_pipeline
from sleep_ai_scientist.grounding.grounding_pipeline import generate_grounding_report, run_grounding_pipeline
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline
from sleep_ai_scientist.hypothesis.co_scientist_pipeline import generate_co_scientist_report, run_co_scientist_pipeline
from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline
from sleep_ai_scientist.benchmark.benchmark_pipeline import generate_benchmark_report, run_benchmark_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI surface for foundation, grounding, scientific loop, and Co-Scientist."""
    parser = argparse.ArgumentParser(prog="sleep_ai_scientist")
    sub = parser.add_subparsers(dest="domain", required=True)
    foundation = sub.add_parser("foundation")
    foundation_sub = foundation.add_subparsers(dest="command", required=True)
    for command in ("build", "report"):
        item = foundation_sub.add_parser(command)
        item.add_argument("--config", default="configs/foundation_config.yaml")
    grounding = sub.add_parser("grounding")
    grounding_sub = grounding.add_subparsers(dest="command", required=True)
    for command in ("build", "report"):
        item = grounding_sub.add_parser(command)
        item.add_argument("--config", default="configs/grounding_config.yaml")
        item.add_argument("--enable-api", action="store_true", help="Enable optional external literature API retrieval for this run.")
    hypothesis = sub.add_parser("hypothesis")
    hypothesis_sub = hypothesis.add_subparsers(dest="command", required=True)
    item = hypothesis_sub.add_parser("build")
    item.add_argument("--config", default="configs/hypothesis_config.yaml")
    experiment = sub.add_parser("experiment")
    experiment_sub = experiment.add_subparsers(dest="command", required=True)
    item = experiment_sub.add_parser("run")
    item.add_argument("--config", default="configs/experiment_config.yaml")
    scientific_loop = sub.add_parser("scientific-loop")
    scientific_loop_sub = scientific_loop.add_subparsers(dest="command", required=True)
    item = scientific_loop_sub.add_parser("run")
    item.add_argument("--hypothesis-config", default="configs/hypothesis_config.yaml")
    item.add_argument("--experiment-config", default="configs/experiment_config.yaml")
    co_scientist = sub.add_parser("co-scientist")
    co_sub = co_scientist.add_subparsers(dest="command", required=True)
    for command in ("run", "report"):
        item = co_sub.add_parser(command)
        item.add_argument("--config", default="configs/co_scientist_config.yaml")
    benchmark = sub.add_parser("benchmark")
    benchmark_sub = benchmark.add_subparsers(dest="command", required=True)
    for command in ("run", "report"):
        item = benchmark_sub.add_parser(command)
        item.add_argument("--config", default="configs/benchmark_config.yaml")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch CLI commands and print a machine-readable run summary."""
    args = build_parser().parse_args(argv)
    if args.domain == "foundation" and args.command == "build":
        result = run_foundation_pipeline(args.config)
    elif args.domain == "foundation" and args.command == "report":
        result = generate_foundation_report(args.config)
    elif args.domain == "grounding" and args.command == "build":
        if getattr(args, "enable_api", False):
            args.config = _enable_api_config(args.config)
        result = run_grounding_pipeline(args.config)
    elif args.domain == "grounding" and args.command == "report":
        if getattr(args, "enable_api", False):
            args.config = _enable_api_config(args.config)
        result = generate_grounding_report(args.config)
    elif args.domain == "hypothesis" and args.command == "build":
        result = run_hypothesis_pipeline(args.config)
    elif args.domain == "experiment" and args.command == "run":
        result = run_experiment_pipeline(args.config)
    elif args.domain == "scientific-loop" and args.command == "run":
        hypothesis_result = run_hypothesis_pipeline(args.hypothesis_config)
        experiment_result = run_experiment_pipeline(args.experiment_config)
        result = {"hypothesis": hypothesis_result, "experiment": experiment_result}
    elif args.domain == "co-scientist" and args.command == "run":
        result = run_co_scientist_pipeline(args.config)
    elif args.domain == "co-scientist" and args.command == "report":
        result = generate_co_scientist_report(args.config)
    elif args.domain == "benchmark" and args.command == "run":
        result = run_benchmark_pipeline(args.config)
    elif args.domain == "benchmark" and args.command == "report":
        result = generate_benchmark_report(args.config)
    else:
        raise ValueError(f"Unsupported command: {args}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _enable_api_config(config_path: str) -> str:
    from pathlib import Path
    import yaml

    from sleep_ai_scientist.common.config import resolve_path

    path = resolve_path(config_path)
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config.setdefault("api", {})["enabled"] = True
    temp_path = Path("/tmp/sleepagent_grounding_enable_api.yaml")
    temp_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return str(temp_path)


if __name__ == "__main__":
    raise SystemExit(main())
