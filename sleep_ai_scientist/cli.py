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
        item.add_argument("--enable-api", action="store_true", help="Enable optional external literature API retrieval for this run.")
        item.add_argument("--disable-api", action="store_true", help="Disable external literature API retrieval for this run.")
        item.add_argument("--query-config", default=None, help="Versioned literature query set YAML.")
        item.add_argument("--corpus-version", default="sleepagent_grounding_corpus_v1")
    literature = sub.add_parser("literature")
    literature_sub = literature.add_subparsers(dest="command", required=True)
    item = literature_sub.add_parser("build")
    item.add_argument("--config", default="configs/literature_library_config.yaml")
    item.add_argument("--query-config", default="configs/literature_queries.yaml")
    item.add_argument("--library-version", default="sleep_literature_library_v1")
    item.add_argument("--backend", default="sqlite")
    item.add_argument("--enable-api", action="store_true")
    item.add_argument("--disable-api", action="store_true")
    item.add_argument("--enable-rag-index", action="store_true")
    db = sub.add_parser("db")
    db_sub = db.add_subparsers(dest="command", required=True)
    for command in ("healthcheck", "init"):
        item = db_sub.add_parser(command)
        item.add_argument("--config", default="configs/database_config.yaml")
        item.add_argument("--backend", default="sqlite")
    knowledge = sub.add_parser("knowledge")
    knowledge_sub = knowledge.add_subparsers(dest="command", required=True)
    for command in ("build", "report", "export"):
        item = knowledge_sub.add_parser(command)
        item.add_argument("--config", default="configs/knowledge_sources_config.yaml")
        item.add_argument("--backend", default="sqlite")
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
            args.config = _set_api_enabled(args.config, True)
        if getattr(args, "disable_api", False):
            args.config = _set_api_enabled(args.config, False)
        result = run_grounding_pipeline(args.config, query_config_path=args.query_config, corpus_version=args.corpus_version)
    elif args.domain == "grounding" and args.command == "report":
        if getattr(args, "enable_api", False):
            args.config = _set_api_enabled(args.config, True)
        if getattr(args, "disable_api", False):
            args.config = _set_api_enabled(args.config, False)
        result = run_grounding_pipeline(args.config, query_config_path=args.query_config, corpus_version=args.corpus_version)
    elif args.domain == "literature" and args.command == "build":
        from sleep_ai_scientist.literature.library_builder import run_literature_build

        api_enabled = True if args.enable_api else False if args.disable_api else None
        result = run_literature_build(
            args.config,
            query_config_path=args.query_config,
            library_version=args.library_version,
            backend=args.backend,
            api_enabled=api_enabled,
            enable_rag_index=args.enable_rag_index,
        )
    elif args.domain == "db" and args.command == "healthcheck":
        from sleep_ai_scientist.storage.healthcheck import check_database_connection

        result = check_database_connection(args.config, backend=args.backend)
    elif args.domain == "db" and args.command == "init":
        from sleep_ai_scientist.storage.db import create_engine_from_config, init_database
        from sleep_ai_scientist.storage.healthcheck import check_database_connection

        engine = create_engine_from_config(args.config, backend=args.backend)
        init_database(engine)
        result = check_database_connection(args.config, backend=args.backend)
        engine.dispose()
    elif args.domain == "knowledge" and args.command == "build":
        from sleep_ai_scientist.knowledge_sources.registry_builder import build_knowledge_sources

        result = build_knowledge_sources(args.config, backend=args.backend)
    elif args.domain == "knowledge" and args.command == "export":
        from sleep_ai_scientist.knowledge_sources.registry_builder import export_knowledge_sources

        result = export_knowledge_sources(args.config, backend=args.backend)
    elif args.domain == "knowledge" and args.command == "report":
        from sleep_ai_scientist.knowledge_sources.registry_builder import generate_knowledge_sources_report

        result = generate_knowledge_sources_report(args.config, backend=args.backend)
    else:
        raise ValueError(f"Unsupported command: {args}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _set_api_enabled(config_path: str, enabled: bool) -> str:
    from pathlib import Path

    import yaml

    from sleep_ai_scientist.common.config import resolve_path

    path = resolve_path(config_path)
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config.setdefault("api", {})["enabled"] = enabled
    suffix = "enable" if enabled else "disable"
    temp_path = Path(f"/tmp/sleepagent_grounding_{suffix}_api.yaml")
    temp_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return str(temp_path)


if __name__ == "__main__":
    raise SystemExit(main())
