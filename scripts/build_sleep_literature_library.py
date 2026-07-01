from __future__ import annotations

import argparse
import json

from sleep_ai_scientist.literature.library_builder import run_literature_build


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/literature_library_config.yaml")
    parser.add_argument("--query-config", default="configs/sleep_literature_queries.yaml")
    parser.add_argument("--library-version", default="sleep_literature_library_v1")
    parser.add_argument("--backend", default=None)
    parser.add_argument("--enable-api", action="store_true")
    parser.add_argument("--disable-api", action="store_true")
    args = parser.parse_args()
    api_enabled = True if args.enable_api else False if args.disable_api else None
    result = run_literature_build(args.config, query_config_path=args.query_config, library_version=args.library_version, backend=args.backend, api_enabled=api_enabled)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
