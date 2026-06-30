from __future__ import annotations

import argparse
import json

from sleep_ai_scientist.foundation.foundation_pipeline import generate_foundation_report, run_foundation_pipeline
from sleep_ai_scientist.grounding.grounding_pipeline import generate_grounding_report, run_grounding_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the narrow Phase 1 CLI surface."""
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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch CLI commands and print a machine-readable run summary."""
    args = build_parser().parse_args(argv)
    if args.domain == "foundation" and args.command == "build":
        result = run_foundation_pipeline(args.config)
    elif args.domain == "foundation" and args.command == "report":
        result = generate_foundation_report(args.config)
    elif args.domain == "grounding" and args.command == "build":
        result = run_grounding_pipeline(args.config)
    elif args.domain == "grounding" and args.command == "report":
        result = generate_grounding_report(args.config)
    else:
        raise ValueError(f"Unsupported command: {args}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
