from __future__ import annotations

import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sleep_ai_scientist.common.io import write_json, write_yaml

RECOVERABLE_ERROR_TYPES = {
    "provider timeout",
    "temporary HTTP error",
    "one query failed",
    "JSON parse failure for one provider response",
    "fulltext download failure",
    "missing citation field",
}
NON_RECOVERABLE_ERROR_TYPES = {
    "schema corruption",
    "manifest cannot be written",
    "output directory not writable",
    "repeated stage failure",
    "config missing required sections",
    "database write failure",
}


def is_recoverable_error(error_type: str, *, fail_open: bool = True) -> bool:
    if error_type in NON_RECOVERABLE_ERROR_TYPES:
        return False
    if error_type == "database write failure" and not fail_open:
        return False
    return error_type in RECOVERABLE_ERROR_TYPES or fail_open


def write_error_bundle(run_dir: str | Path, error: BaseException, stage: str, config: dict[str, Any] | None = None, query_config: dict[str, Any] | None = None, latest_checkpoint: dict[str, Any] | None = None, command: str = "") -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle = Path(run_dir) / "errors" / f"error_bundle_{timestamp}"
    bundle.mkdir(parents=True, exist_ok=True)
    write_json(bundle / "error_summary.json", {"stage": stage, "error_type": type(error).__name__, "message": str(error), "timestamp": datetime.now(timezone.utc).isoformat()})
    (bundle / "traceback.txt").write_text("".join(traceback.format_exception(type(error), error, error.__traceback__)), encoding="utf-8")
    (bundle / "failed_stage.txt").write_text(stage, encoding="utf-8")
    write_json(bundle / "latest_checkpoint.json", latest_checkpoint or {})
    write_yaml(bundle / "current_config.yaml", config or {})
    write_yaml(bundle / "current_query_config.yaml", query_config or {})
    (bundle / "reproduction_command.sh").write_text((command or "python -m sleep_ai_scientist.cli literature long-run --config configs/literature_long_run_config.yaml --resume <checkpoint_path>") + "\n", encoding="utf-8")
    (bundle / "suggested_debug_steps.md").write_text("# Suggested Debug Steps\n\n- Inspect error_summary.json.\n- Re-run from latest checkpoint if the error is recoverable.\n- Validate database connectivity and output directory permissions.\n", encoding="utf-8")
    return bundle

