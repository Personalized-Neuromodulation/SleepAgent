from __future__ import annotations

import argparse
import json

from sleep_ai_scientist.literature.long_run_supervisor import run_long_run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/literature_long_run_config.yaml")
    parser.add_argument("--max-runtime-hours", type=float, default=None)
    parser.add_argument("--resume", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backend", default="sqlite")
    args = parser.parse_args()
    result = run_long_run(args.config, max_runtime_hours=args.max_runtime_hours, resume=args.resume, dry_run=args.dry_run, backend=args.backend)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

