#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export SLEEPAGENT_SQLITE_PATH="$ROOT_DIR/data/literature/sleep_literature.db"
export PYTHONUNBUFFERED=1
export SLEEPAGENT_API_VERBOSE=1

mkdir -p data/literature data/knowledge_sources outputs/grounding outputs/knowledge_sources outputs/profiles reports

echo "[1/6] Build no-real-data foundation"
python -m sleep_ai_scientist.cli foundation build \
  --config configs/foundation_no_real_data.yaml

echo "[2/6] Run online grounding without fixture fallback"
python -u - <<'PY'
import json
from sleep_ai_scientist.common.config import load_config
from sleep_ai_scientist.api.literature_client import apply_query_config
from sleep_ai_scientist.grounding.grounding_pipeline import run_grounding_pipeline

config = load_config("configs/grounding_online_no_fixtures.yaml")
config = apply_query_config(config, "configs/literature_queries.yaml")
api_cfg = config.setdefault("api", {})
api_cfg["enabled"] = True
api_cfg["fail_open"] = True
api_cfg["verbose"] = True
api_cfg.setdefault("providers", {}).setdefault("openalex", {})["min_interval_seconds"] = 5
tmp_config = "/tmp/sleepagent_grounding_online_no_fixtures.yaml"

import yaml
from pathlib import Path
payload = dict(config)
payload.pop("_config_path", None)
payload.pop("_project_root", None)
Path(tmp_config).write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

providers = [
    name
    for name, provider_cfg in api_cfg.get("providers", {}).items()
    if provider_cfg.get("enabled", False)
]
print(
    json.dumps(
        {
            "grounding_config": tmp_config,
            "providers": providers,
            "query_count": len(api_cfg.get("search_queries", [])),
            "max_results_per_query": api_cfg.get("max_results_per_query"),
            "allow_fixtures": config.get("runtime", {}).get("allow_fixtures"),
            "output_grounding_dir": config.get("paths", {}).get("output_grounding_dir"),
        },
        ensure_ascii=False,
        indent=2,
    ),
    flush=True,
)

result = run_grounding_pipeline(
    tmp_config,
    query_config_path=None,
    corpus_version="sleepagent_grounding_online_no_real_data_v1",
)
print(json.dumps(result, ensure_ascii=False, indent=2))
PY

echo "[3/6] Build knowledge source registry"
python -m sleep_ai_scientist.cli knowledge build \
  --config configs/knowledge_sources_config.yaml \
  --backend sqlite

echo "[4/6] Build online sleep literature SQLite DB"
python -m sleep_ai_scientist.cli literature build \
  --config configs/literature_library_config.yaml \
  --query-config configs/sleep_literature_queries.yaml \
  --library-version sleep_literature_library_v1_online_no_real_data \
  --backend sqlite \
  --enable-api

echo "[5/6] Validate core grounding outputs, literature DB, and knowledge sources"
python - <<'PY'
import json
import sqlite3
from pathlib import Path

evidence_path = Path("outputs/grounding/evidence_table.json")
graph_path = Path("outputs/grounding/mechanism_graph.json")
manifest_path = Path("outputs/grounding/corpus_manifest.json")
foundation_manifest_path = Path("data/foundation/foundation_manifest.json")
db_path = Path("data/literature/sleep_literature.db")

required = [evidence_path, graph_path, manifest_path, foundation_manifest_path, db_path]
missing = [str(path) for path in required if not path.exists()]
if missing:
    raise SystemExit(f"Missing required outputs: {missing}")

evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
graph = json.loads(graph_path.read_text(encoding="utf-8"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
foundation_manifest = json.loads(foundation_manifest_path.read_text(encoding="utf-8"))

api_summary = manifest.get("api_summary", {})
raw_count = int(api_summary.get("raw_count", 0) or 0)
final_count = int(api_summary.get("final_literature_count", 0) or 0)
node_count = len(graph.get("nodes", []))
edge_count = len(graph.get("edges", []))

if foundation_manifest.get("foundation_mode") != "no_real_data":
    raise SystemExit("Foundation manifest is not no_real_data mode")
if raw_count <= 0:
    raise SystemExit("Online API retrieval returned zero raw records")
if final_count <= 0:
    raise SystemExit("No literature records were registered")
if len(evidence) <= 0:
    raise SystemExit("No evidence records were extracted")
if node_count <= 0 or edge_count <= 0:
    raise SystemExit("Mechanism graph is empty")
if any(str(item.get("paper_id", "")).startswith("toy") for item in evidence):
    raise SystemExit("Fixture/toy evidence leaked into online grounding output")

with sqlite3.connect(db_path) as conn:
    db_counts = {
        "papers": conn.execute("select count(*) from papers").fetchone()[0],
        "queries": conn.execute("select count(*) from queries").fetchone()[0],
        "query_results": conn.execute("select count(*) from query_results").fetchone()[0],
        "corpus_versions": conn.execute("select count(*) from corpus_versions").fetchone()[0],
        "build_runs": conn.execute("select count(*) from build_runs").fetchone()[0],
        "guidelines": conn.execute("select count(*) from guidelines").fetchone()[0],
        "standards_rules": conn.execute("select count(*) from standards_rules").fetchone()[0],
        "diagnostic_terms": conn.execute("select count(*) from diagnostic_terms").fetchone()[0],
        "datasets": conn.execute("select count(*) from datasets").fetchone()[0],
        "instruments": conn.execute("select count(*) from instruments").fetchone()[0],
        "tools_methods": conn.execute("select count(*) from tools_methods").fetchone()[0],
    }

empty_tables = [name for name, count in db_counts.items() if int(count) <= 0]
if empty_tables:
    raise SystemExit(f"Literature DB has empty required tables: {empty_tables}")

print({
    "api_raw_count": raw_count,
    "registered_literature_count": final_count,
    "evidence_count": len(evidence),
    "graph_nodes": node_count,
    "graph_edges": edge_count,
    "literature_db": str(db_path),
    "db_counts": db_counts,
})
PY

echo "[6/6] Run targeted no-real-data foundation/grounding, DB, and knowledge source tests"
python -m pytest tests/test_no_real_data_foundation_grounding.py tests/test_literature_db_generation.py tests/test_knowledge_source_generation.py tests/test_knowledge_sources_db_integration.py

echo "Done. Core outputs:"
echo "  outputs/grounding/evidence_table.json"
echo "  outputs/grounding/mechanism_graph.json"
echo "  data/literature/sleep_literature.db"
echo "  outputs/knowledge_sources/knowledge_sources_manifest.json"
