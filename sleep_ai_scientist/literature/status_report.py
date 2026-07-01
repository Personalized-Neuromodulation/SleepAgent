from __future__ import annotations

from pathlib import Path
from typing import Any


def build_status_report(status: dict[str, Any]) -> str:
    lines = [
        "# Sleep Literature Long-Run Status",
        "",
        f"- run_id: {status.get('run_id', '')}",
        f"- elapsed time: {status.get('elapsed_time', '')}",
        f"- current iteration: {status.get('current_iteration', 0)}",
        f"- current stage: {status.get('current_stage', '')}",
        f"- total records: {status.get('total_records', 0)}",
        f"- new records this hour: {status.get('new_records_this_hour', 0)}",
        f"- duplicate rate: {status.get('duplicate_rate', 0)}",
        f"- coverage summary: {status.get('coverage_summary', {})}",
        f"- provider health: {status.get('provider_health', {})}",
        f"- sparse query groups: {status.get('sparse_query_groups', [])}",
        f"- last checkpoint: {status.get('last_checkpoint', '')}",
        f"- warnings: {status.get('warnings', [])}",
        f"- errors: {status.get('errors', [])}",
        f"- next planned iteration: {status.get('next_planned_iteration', '')}",
        "",
    ]
    return "\n".join(lines)


def write_status_report(run_dir: str | Path, hour_index: int, status: dict[str, Any]) -> Path:
    report_dir = Path(run_dir) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"status_{hour_index:03d}.md"
    path.write_text(build_status_report(status), encoding="utf-8")
    return path

