from __future__ import annotations

import argparse
import json

from sleep_ai_scientist.foundation.foundation_pipeline import generate_foundation_report, run_foundation_pipeline
from sleep_ai_scientist.grounding.grounding_pipeline import generate_grounding_report, run_grounding_pipeline
from sleep_ai_scientist.hypothesis.hypothesis_pipeline import run_hypothesis_pipeline
from sleep_ai_scientist.hypothesis.co_scientist_pipeline import generate_co_scientist_report, run_co_scientist_pipeline
from sleep_ai_scientist.experiment.experiment_pipeline import run_experiment_pipeline
from sleep_ai_scientist.benchmark.benchmark_pipeline import generate_benchmark_report, run_benchmark_pipeline
from sleep_ai_scientist.literature.library_builder import run_literature_build
from sleep_ai_scientist.literature.long_run_supervisor import run_long_run
from sleep_ai_scientist.knowledge_sources.registry_builder import build_knowledge_sources, export_knowledge_sources, generate_knowledge_sources_report
from sleep_ai_scientist.storage.db import create_engine_from_config, init_database, session_scope
from sleep_ai_scientist.storage.exporters import export_phase1_literature_artifacts
from sleep_ai_scientist.storage.healthcheck import check_database_connection


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
        item.add_argument("--disable-api", action="store_true", help="Disable external literature API retrieval for this run.")
        item.add_argument("--query-config", default=None, help="Versioned literature query set YAML.")
        item.add_argument("--corpus-version", default="sleepagent_grounding_corpus_v1")
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
    db = sub.add_parser("db")
    db_sub = db.add_subparsers(dest="command", required=True)
    item = db_sub.add_parser("healthcheck")
    item.add_argument("--config", default="configs/database_config.yaml")
    item.add_argument("--backend", default=None)
    item = db_sub.add_parser("init")
    item.add_argument("--config", default="configs/database_config.yaml")
    item.add_argument("--backend", default=None)
    item = db_sub.add_parser("export")
    item.add_argument("--config", default="configs/database_config.yaml")
    item.add_argument("--corpus-version", default="sleep_literature_library_v1")
    item.add_argument("--backend", default=None)
    literature = sub.add_parser("literature")
    literature_sub = literature.add_subparsers(dest="command", required=True)
    item = literature_sub.add_parser("build")
    item.add_argument("--config", default="configs/literature_library_config.yaml")
    item.add_argument("--query-config", default="configs/sleep_literature_queries.yaml")
    item.add_argument("--library-version", default="sleep_literature_library_v1")
    item.add_argument("--backend", default=None)
    item.add_argument("--enable-api", action="store_true")
    item.add_argument("--disable-api", action="store_true")
    item = literature_sub.add_parser("long-run")
    item.add_argument("--config", default="configs/literature_long_run_config.yaml")
    item.add_argument("--max-runtime-hours", type=float, default=None)
    item.add_argument("--resume", default=None)
    item.add_argument("--dry-run", action="store_true")
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
            args.config = _enable_api_config(args.config)
        if getattr(args, "disable_api", False):
            args.config = _disable_api_config(args.config)
        result = run_grounding_pipeline(args.config, query_config_path=args.query_config, corpus_version=args.corpus_version)
    elif args.domain == "grounding" and args.command == "report":
        if getattr(args, "enable_api", False):
            args.config = _enable_api_config(args.config)
        if getattr(args, "disable_api", False):
            args.config = _disable_api_config(args.config)
        result = run_grounding_pipeline(args.config, query_config_path=args.query_config, corpus_version=args.corpus_version)
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
    elif args.domain == "db" and args.command == "healthcheck":
        result = check_database_connection(args.config, backend=args.backend)
    elif args.domain == "db" and args.command == "init":
        engine = create_engine_from_config(args.config, backend=args.backend)
        init_database(engine)
        result = check_database_connection(args.config, backend=args.backend)
        engine.dispose()
    elif args.domain == "db" and args.command == "export":
        engine = create_engine_from_config(args.config, backend=args.backend)
        with session_scope(engine) as session:
            result = export_phase1_literature_artifacts(
                session,
                args.corpus_version,
                {
                    "registry_csv": "data/literature/sleep_literature_registry.csv",
                    "registry_jsonl": "data/literature/sleep_literature_registry.jsonl",
                    "query_summary": "outputs/literature/query_summary.csv",
                    "provider_summary": "outputs/literature/provider_summary.json",
                    "manifest": "outputs/literature/sleep_library_manifest.json",
                },
            )
        engine.dispose()
    elif args.domain == "literature" and args.command == "build":
        api_enabled = True if args.enable_api else False if args.disable_api else None
        result = run_literature_build(args.config, query_config_path=args.query_config, library_version=args.library_version, backend=args.backend, api_enabled=api_enabled)
    elif args.domain == "literature" and args.command == "long-run":
        result = run_long_run(args.config, max_runtime_hours=args.max_runtime_hours, resume=args.resume, dry_run=args.dry_run, backend=args.backend)
    elif args.domain == "knowledge" and args.command == "build":
        result = build_knowledge_sources(args.config, backend=args.backend)
    elif args.domain == "knowledge" and args.command == "export":
        result = export_knowledge_sources(args.config, backend=args.backend)
    elif args.domain == "knowledge" and args.command == "report":
        result = generate_knowledge_sources_report(args.config, backend=args.backend)
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


def _disable_api_config(config_path: str) -> str:
    from pathlib import Path
    import yaml

    from sleep_ai_scientist.common.config import resolve_path

    path = resolve_path(config_path)
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config.setdefault("api", {})["enabled"] = False
    temp_path = Path("/tmp/sleepagent_grounding_disable_api.yaml")
    temp_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return str(temp_path)


if __name__ == "__main__":
    raise SystemExit(main())
